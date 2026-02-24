import os
import boto3
import genai_core.types
import genai_core.chunks
import genai_core.documents
import genai_core.workspaces
import genai_core.aurora.create
from langchain_community.document_loaders import S3FileLoader

WORKSPACE_ID = os.environ.get("WORKSPACE_ID")
DOCUMENT_ID = os.environ.get("DOCUMENT_ID")
CONNECTOR_ID = os.environ.get("CONNECTOR_ID")
FILE_PATH = os.environ.get("FILE_PATH")
INPUT_BUCKET_NAME = os.environ.get("INPUT_BUCKET_NAME")
INPUT_OBJECT_KEY = os.environ.get("INPUT_OBJECT_KEY")
PROCESSING_BUCKET_NAME = os.environ.get("PROCESSING_BUCKET_NAME")
PROCESSING_OBJECT_KEY = os.environ.get("PROCESSING_OBJECT_KEY")

s3_client = boto3.client("s3")


def main():
    print("Starting file converter batch job")
    print("Workspace ID: {}".format(WORKSPACE_ID))
    print("Document ID: {}".format(DOCUMENT_ID))
    is_connector_import = bool(CONNECTOR_ID and FILE_PATH)

    if is_connector_import:
        print("Connector import: connector_id={}, file_path={}".format(CONNECTOR_ID, FILE_PATH))
    else:
        print("Input bucket name: {}".format(INPUT_BUCKET_NAME))
        print("Input object key: {}".format(INPUT_OBJECT_KEY))
    print("Processing bucket name: {}".format(PROCESSING_BUCKET_NAME))
    print("Processing object key: {}".format(PROCESSING_OBJECT_KEY))

    workspace = genai_core.workspaces.get_workspace(WORKSPACE_ID)
    if not workspace:
        raise genai_core.types.CommonError(f"Workspace {WORKSPACE_ID} does not exist")

    document = genai_core.documents.get_document(WORKSPACE_ID, DOCUMENT_ID)
    if not document:
        raise genai_core.types.CommonError(
            f"Document {WORKSPACE_ID}/{DOCUMENT_ID} does not exist"
        )

    try:
        if is_connector_import:
            from genai_core.connectors import connector_files
            content_bytes = connector_files.fetch_file_content(
                connector_id=CONNECTOR_ID,
                workspace_id=WORKSPACE_ID,
                file_path=FILE_PATH,
            )
            s3_client.put_object(
                Bucket=PROCESSING_BUCKET_NAME,
                Key=PROCESSING_OBJECT_KEY,
                Body=content_bytes,
            )
            input_bucket = PROCESSING_BUCKET_NAME
            input_key = PROCESSING_OBJECT_KEY
        else:
            input_bucket = INPUT_BUCKET_NAME
            input_key = INPUT_OBJECT_KEY

        extension = os.path.splitext(input_key)[-1].lower()
        if extension == ".txt":
            obj = s3_client.get_object(Bucket=input_bucket, Key=input_key)
            content = obj["Body"].read().decode("utf-8")
        else:
            loader = S3FileLoader(input_bucket, input_key)
            print("loader: {}".format(loader))
            docs = loader.load()
            content = docs[0].page_content

        if input_bucket != PROCESSING_BUCKET_NAME or input_key != PROCESSING_OBJECT_KEY:
            s3_client.put_object(
                Bucket=PROCESSING_BUCKET_NAME,
                Key=PROCESSING_OBJECT_KEY,
                Body=content,
            )

        add_chunks(workspace, document, content)
    except Exception as error:
        genai_core.documents.set_status(WORKSPACE_ID, DOCUMENT_ID, "error")
        print(error)
        raise error


def add_chunks(workspace: dict, document: dict, content: str):
    chunks = genai_core.chunks.split_content(workspace, content)

    genai_core.chunks.add_chunks(
        workspace=workspace,
        document=document,
        document_sub_id=None,
        chunks=chunks,
        chunk_complements=None,
        replace=True,
    )


if __name__ == "__main__":
    main()

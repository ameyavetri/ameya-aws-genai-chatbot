import os
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from adapters.base import ModelAdapter
from genai_core.registry import registry
from adapters.shared.prompts.system_prompts import prompts, locale
from adapters.shared.prompts.staffing_prompts import STAFFING_PROMPTS
from aws_lambda_powertools import Logger

logger = Logger()


class GPTAdapter(ModelAdapter):
    def __init__(self, model_id, *args, **kwargs):
        self.model_id = model_id
        self.user_intent = kwargs.pop('user_intent', None)
        self.job_description = kwargs.pop('job_description', None)
        super().__init__(*args, **kwargs)

    def get_llm(self, model_kwargs={}):
        if not os.environ.get("OPENAI_API_KEY"):
            raise Exception("OPENAI_API_KEY must be set in the environment")

        params = {}
        if "streaming" in model_kwargs:
            params["streaming"] = model_kwargs["streaming"]
        if "temperature" in model_kwargs:
            params["temperature"] = model_kwargs["temperature"]
        if "maxTokens" in model_kwargs:
            params["max_tokens"] = model_kwargs["maxTokens"]

        return ChatOpenAI(
            model_name=self.model_id, 
            callbacks=[self.callback_handler], 
            **params
        )
    
    def _get_staffing_prompt_config(self):
        """Get the appropriate staffing prompt based on user intent"""
        if not self.user_intent:
            return STAFFING_PROMPTS[locale]["general"]
        
        intent_value = self.user_intent.value if hasattr(self.user_intent, 'value') else str(self.user_intent)
        
        logger.info(f"Getting staffing prompt for intent: {intent_value}")
        
        return STAFFING_PROMPTS[locale].get(
            intent_value,
            STAFFING_PROMPTS[locale]["general"]
        )
    
    def get_prompt(self, custom_prompt=None):
        """
        Get the conversation prompt for GPT models (non-RAG mode)
        Compatible with ConversationChain which uses {input} and {chat_history}
        """
        if custom_prompt:
            conversation_prompt = custom_prompt
        else:
            prompt_config = self._get_staffing_prompt_config()
            conversation_prompt = prompt_config.get(
                "system_prompt",
                prompts[locale]["conversation_prompt"]
            )
        
        # ConversationChain expects {input} and {chat_history}
        template = f"""{conversation_prompt}

Current conversation:
{{chat_history}}

Question: {{input}}"""
        
        logger.info(f"Using conversation prompt for intent: {self.user_intent}")
        
        return PromptTemplate.from_template(template)
    
    def get_qa_prompt(self, custom_prompt=None):
        """
        Get the QA prompt for GPT models with RAG context
        Compatible with ConversationalRetrievalChain's combine_docs_chain
        
        The combine_docs_chain expects: {context}, {question}
        """
        if custom_prompt:
            qa_system_prompt = custom_prompt
        else:
            prompt_config = self._get_staffing_prompt_config()
            qa_system_prompt = prompt_config.get(
                "system_prompt",
                prompts[locale]["qa_prompt"]
            )
        
        # For resume assessment with JD
        intent_val = self.user_intent.value if hasattr(self.user_intent, "value") else str(self.user_intent) if self.user_intent else None
        if self.job_description and intent_val == "resume_assessment":
            qa_full_prompt = f"""{qa_system_prompt}

## Job Description:
{self.job_description}

## Candidate Resumes (Retrieved from Workspace):
{{context}}

## Question:
{{question}}

## Answer:"""
        else:
            # Standard RAG prompt
            qa_full_prompt = f"""{qa_system_prompt}

Context:
{{context}}

Question: {{question}}

Answer:"""
        
        logger.info(f"Using QA prompt for intent: {self.user_intent}, with JD: {bool(self.job_description)}")
        
        # Return as PromptTemplate (NOT ChatPromptTemplate)
        # ConversationalRetrievalChain's combine_docs_chain expects PromptTemplate
        return PromptTemplate(
            template=qa_full_prompt,
            input_variables=["context", "question"]
        )
    
    def get_condense_question_prompt(self, custom_prompt=None):
        """
        Get the condense question prompt for follow-up questions
        Compatible with ConversationalRetrievalChain's question_generator
        
        Expects: {chat_history}, {question}
        """
        if custom_prompt:
            condense_prompt = custom_prompt
        else:
            condense_prompt = prompts[locale]["condense_question_prompt"]
        
        # ConversationalRetrievalChain's question generator expects PromptTemplate
        # with {chat_history} and {question}
        template = f"""{condense_prompt}

Chat History:
{{chat_history}}

Follow Up Question: {{question}}

Standalone Question:"""
        
        return PromptTemplate(
            template=template,
            input_variables=["chat_history", "question"]
        )
# Register the adapter
registry.register(r"^openai\..*", GPTAdapter)
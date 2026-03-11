import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";
import Chat from "../../components/chatbot/chat";
import styles from "../../styles/chat.module.scss";

export default function ApplicationChat() {
  const { applicationId, sessionId } = useParams();
  const navigate = useNavigate();

  // Persist session in URL so chat history is retained across refreshes
  useEffect(() => {
    if (applicationId && !sessionId) {
      const newSessionId = uuidv4();
      navigate(`/application/${applicationId}/${newSessionId}`, {
        replace: true,
      });
    }
  }, [applicationId, sessionId, navigate]);

  // Don't render Chat until we have a sessionId (avoid flash before redirect)
  if (applicationId && !sessionId) {
    return null;
  }

  return (
    <div
      className={styles.appChatContainer}
      data-locator="chatbot-ai-container"
    >
      <Chat sessionId={sessionId} applicationId={applicationId} />
    </div>
  );
}

import re
from typing import Dict, Optional, Tuple
from enum import Enum
from aws_lambda_powertools import Logger

logger = Logger()


class UserIntent(Enum):
    """Define all possible user intents"""
    JOB_POSTING_CREATION = "job_posting_creation"
    RESUME_ASSESSMENT = "resume_assessment"
    QA_MODE = "qa_mode"
    GENERAL = "general"


class IntentDetector:
    """Detects user intent and extracts structured information"""
    
    # Intent detection patterns
    INTENT_PATTERNS = {
        UserIntent.JOB_POSTING_CREATION: [
            r"(?:analyze|review|check|parse|extract from|look at).*?(?:job description|jd|job posting|job requirement)",
            r"(?:create|generate|write|prepare|draft|make).*?(?:job posting|job ad|posting)",
            r"(?:what|which).*?(?:skills|requirements|qualifications).*?(?:needed|required)",
            r"job\s+description[:\s]",
            r"jd[:\s]",
        ],
        UserIntent.RESUME_ASSESSMENT: [
            r"(?:assess|evaluate|review|analyze|check|match|compare).*?(?:resume|cv|candidate|profile)",
            r"(?:search|find|look for|pull|get|fetch).*?(?:resume|cv|candidate|profile)",
            r"(?:search|find|look for|check).*?(?:workspace|database|rag)",
            r"(?:workspace|database).*?(?:resume|cv|candidate|profile)",
            r"(?:should i|can i|ready to).*?submit.*?(?:candidate|profile|resume)",
            r"(?:match|fit|suitable).*?(?:for|against|with).*?(?:job|position|role|jd)",
            r"(?:candidate|resume|profile).*?(?:match|suitable|qualified)",
            r"screen.*?(?:resume|candidate|profile)",
            r"(?:can you|please|now).*?(?:check|verify|search|find).*?(?:resume|workspace|candidate)",
        ],
        UserIntent.QA_MODE: [
            r"^(?:what|why|how|when|where|who|which|can you|could you|please|tell me)",
            r"(?:explain|clarify|elaborate|describe|details about)",
            r"(?:more information|further details|specific|particular).*about",
            r"(?:difference between|compare.*and)",
        ]
    }
    
    # Job Description extraction patterns
    JD_MARKERS = [
        r"job description[:\s]+(.+?)(?=\n\n|$)",
        r"jd[:\s]+(.+?)(?=\n\n|$)",
        r"job requirement[s]?[:\s]+(.+?)(?=\n\n|$)",
        r"position[:\s]+(.+?)(?=\n\n|$)",
        r"role[:\s]+(.+?)(?=requirements|skills|qualifications|\n\n|$)",
    ]
    
    @classmethod
    def analyze_query(
        cls,
        user_prompt: str,
        workspace_id: Optional[str] = None,
        session_history: Optional[list] = None
    ) -> Dict:
        """
        Analyze user query and extract intent, job description, and clean query
        
        Returns:
            {
                'intent': UserIntent,
                'job_description': str or None,
                'clean_query': str,
                'has_jd': bool,
                'requires_rag': bool
            }
        """
        # Detect intent
        intent = cls._detect_intent(user_prompt, workspace_id, session_history)
        
        # Extract job description if present
        job_description, clean_query = cls._extract_job_description(user_prompt)
        
        # Determine if RAG retrieval is needed
        requires_rag = cls._requires_rag_retrieval(intent, job_description is not None)
        
        result = {
            'intent': intent,
            'job_description': job_description,
            'clean_query': clean_query,
            'has_jd': job_description is not None,
            'requires_rag': requires_rag,
            'workspace_id': workspace_id
        }
        
        logger.info("Query analysis complete", **{k: v for k, v in result.items() if k != 'job_description'})
        
        return result
    
    @classmethod
    def _detect_intent(
        cls,
        user_prompt: str,
        workspace_id: Optional[str],
        session_history: Optional[list]
    ) -> UserIntent:
        """Detect user intent from query patterns"""
        prompt_lower = user_prompt.lower()
        
        # Score each intent based on pattern matching
        scores = {intent: 0 for intent in UserIntent}
        
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, prompt_lower, re.IGNORECASE | re.DOTALL):
                    scores[intent] += 1
        
        # Additional context-based scoring
        if workspace_id:
            # If workspace exists, likely doing resume work
            if any(word in prompt_lower for word in ['resume', 'candidate', 'cv', 'profile']):
                scores[UserIntent.RESUME_ASSESSMENT] += 2
        
        if 'job description' in prompt_lower or 'jd:' in prompt_lower or 'jd ' in prompt_lower:
            if any(word in prompt_lower for word in ['create', 'generate', 'extract', 'analyze']):
                scores[UserIntent.JOB_POSTING_CREATION] += 3
            elif any(word in prompt_lower for word in ['assess', 'match', 'evaluate', 'compare']):
                scores[UserIntent.RESUME_ASSESSMENT] += 2
        
        # Check session history for context
        if session_history:
            recent_intent = cls._infer_from_history(session_history)
            if recent_intent:
                scores[recent_intent] += 1
        
        # Get highest scoring intent
        max_score = max(scores.values())
        if max_score == 0:
            return UserIntent.GENERAL
        
        detected_intent = max(scores, key=scores.get)
        
        logger.info("Intent detection scores", scores={k.value: v for k, v in scores.items()})
        
        return detected_intent
    
    @classmethod
    def _extract_job_description(cls, user_prompt: str) -> Tuple[Optional[str], str]:
        """
        Extract job description from user prompt
        
        Returns:
            (job_description, clean_query) tuple
        """
        # Try each JD marker pattern
        for pattern in cls.JD_MARKERS:
            match = re.search(pattern, user_prompt, re.IGNORECASE | re.DOTALL)
            if match:
                jd_text = match.group(1).strip()
                # Remove the JD portion from the query
                clean_query = re.sub(pattern, '', user_prompt, flags=re.IGNORECASE | re.DOTALL).strip()
                
                logger.info("Job description extracted", jd_length=len(jd_text), clean_query_length=len(clean_query))
                
                return jd_text, clean_query
        
        # Look for structured JD blocks (markdown code blocks, etc.)
        code_block_match = re.search(r'```(?:text|markdown|)?\s*(.+?)\s*```', user_prompt, re.DOTALL)
        if code_block_match:
            potential_jd = code_block_match.group(1).strip()
            # Check if it looks like a JD (has typical JD keywords)
            if cls._looks_like_jd(potential_jd):
                clean_query = user_prompt.replace(code_block_match.group(0), '').strip()
                return potential_jd, clean_query
        
        # Check if entire prompt is a JD (heuristic)
        if len(user_prompt) > 200 and cls._looks_like_jd(user_prompt):
            # If user just pasted a JD without any query
            return user_prompt, "Analyze this job description and extract key requirements."
        
        return None, user_prompt
    
    @classmethod
    def _looks_like_jd(cls, text: str) -> bool:
        """Heuristic to determine if text looks like a job description"""
        jd_indicators = [
            'responsibilities', 'requirements', 'qualifications', 'skills',
            'experience', 'years', 'bachelor', 'degree', 'must have',
            'nice to have', 'preferred', 'required', 'job title',
            'position', 'role', 'candidate', 'apply'
        ]
        
        text_lower = text.lower()
        matches = sum(1 for indicator in jd_indicators if indicator in text_lower)
        
        # If text has 4+ JD indicators, it's likely a JD
        return matches >= 4
    
    @classmethod
    def _requires_rag_retrieval(cls, intent: UserIntent, has_jd: bool) -> bool:
        """Determine if RAG retrieval is needed"""
        # Resume assessment always needs RAG (to get resumes)
        if intent == UserIntent.RESUME_ASSESSMENT:
            return True
        
        # QA mode might need RAG for context
        if intent == UserIntent.QA_MODE:
            return True
        
        # Job posting creation doesn't need RAG if JD is provided
        if intent == UserIntent.JOB_POSTING_CREATION and has_jd:
            return False
        
        return False
    
    @classmethod
    def _infer_from_history(cls, session_history: list) -> Optional[UserIntent]:
        """Infer intent from conversation history"""
        if not session_history or len(session_history) < 2:
            return None

        recent_text = " ".join(str(msg) for msg in session_history[-5:]).lower()

        if (
            "resume" in recent_text
            or "candidate" in recent_text
            or ("workspace" in recent_text and "checklist" in recent_text)
            or ("checklist" in recent_text and "match" in recent_text)
        ):
            return UserIntent.RESUME_ASSESSMENT
        elif "job description" in recent_text or "posting" in recent_text:
            return UserIntent.JOB_POSTING_CREATION

        return None
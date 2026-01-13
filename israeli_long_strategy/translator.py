import logging
import os
import json
from typing import Dict, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

class RiskTranslator:
    def __init__(self):
        # Use a high-quality model for translation
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("⚠️ GOOGLE_API_KEY not found. Translation will be skipped.")
            self.llm = None
        else:
            # Use Gemini 2.5 Flash as explicitly requested
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash", 
                temperature=0.1,
                convert_system_message_to_human=True
            )

    def translate_analysis(self, results: Dict) -> Dict:
        """
        Translate the analysis results to professional Hebrew.
        """
        enabled = os.getenv("ISRAELI_LONG_ENABLE_TRANSLATION", "0").strip() == "1"
        if not enabled:
            return results

        if not self.llm:
            return results

        logger.info("🌍 Starting Professional Hebrew Translation (Gemini 2.5 Flash)...")
        
        # 1. Translate Top Candidates Recommendation
        for c in results.get("top_long_candidates", []):
            c['recommendation_he'] = self._translate_text(c['recommendation'], context="Financial recommendation")

        # 2. Translate details only for the top candidates (keeps cost + latency under control)
        top = results.get("top_long_candidates", [])[:10]
        top_symbols = {c.get('symbol') for c in top if c.get('symbol')}

        for bucket, companies in results.get("bucket_analysis", {}).items():
            for co in companies:
                if co.get('symbol') in top_symbols:
                    self._translate_company_batch(co)

        return results

    def _translate_company_batch(self, company_data: Dict):
        """
        Translate all fields for a company in a single API call.
        """
        details = company_data.get('details', {})
        
        # Prepare text to translate
        to_translate = {
            "fundamental_reasoning": details.get('fundamental_reasoning_en', ''),
            "macro_reasoning": details.get('macro_reasoning_en', ''),
            "notes": details.get('notes_en', '')
        }
        
        # Filter out empty fields
        to_translate = {k: v for k, v in to_translate.items() if v and v != "N/A"}
        
        if not to_translate:
            return

        prompt = f"""
        You are an expert financial translator. Translate the values of the following JSON to professional Hebrew.
        
        INPUT JSON:
        {json.dumps(to_translate, indent=2)}
        
        GUIDELINES:
        1. Use high-level, professional financial Hebrew (עברית פיננסית מקצועית).
        2. Do not translate proper nouns (Company names) unless standard.
        3. Keep the tone serious and analytical.
        4. Return ONLY the valid JSON with the translated values. Keys must remain unchanged.
        """
        
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            
            # Clean up markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
                
            translated_dict = json.loads(content)
            
            # Update the company data
            if 'fundamental_reasoning' in translated_dict:
                details['fundamental_reasoning_he'] = translated_dict['fundamental_reasoning']
            if 'macro_reasoning' in translated_dict:
                details['macro_reasoning_he'] = translated_dict['macro_reasoning']
            if 'notes' in translated_dict:
                details['notes_he'] = translated_dict['notes']
                
        except Exception as e:
            logger.error(f"Batch translation failed for {company_data.get('symbol')}: {e}")

    def _translate_text(self, text: str, context: str = "") -> str:
        """
        Translate a single string to Hebrew using Gemini.
        """
        if not text or text == "N/A":
            return text

        prompt = f"""
        Translate to professional Hebrew: "{text}"
        Context: {context}
        Output ONLY the translation.
        """
        
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip().replace('"', '')
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return text # Fallback to English

import os
import json
from openai import OpenAI
from pydantic import BaseModel
from typing import List

class TopicExtraction(BaseModel):
    topic: str
    key_points: List[str]

class SlideStructure(BaseModel):
    topics: List[TopicExtraction]

class SlideAnalyzer:
    def __init__(self, api_key: str = None, model: str = \"gpt-4o\"):
        \"\"\"
        Initializes the Slide Analyzer which calls an LLM to extract lecture structure.
        \"\"\"
        self.api_key = api_key or os.environ.get(\"OPENAI_API_KEY\")
        if not self.api_key:
            raise ValueError(\"OpenAI API key must be provided or set in OPENAI_API_KEY env var.\")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def extract_structure(self, slide_text: str) -> List[dict]:
        \"\"\"
        Sends the slide text to the LLM to extract a list of topics in order.
        Returns a list of dictionaries with 'topic' and 'key_points' keys.
        \"\"\"
        prompt = (
            \"You are an expert academic assistant. Your task is to analyze lecture slides \"
            \"and extract the lecture structure.\\n\"
            \"Follow these rules STRICTLY:\\n\"
            \"1. Extract the main topics in the EXACT ORDER they appear in the slides.\\n\"
            \"2. For each topic, extract a few key points based ONLY on the slide text.\\n\"
            \"3. Do not invent topics or add outside information.\\n\"
            \"4. Output your response as a JSON object matching the provided schema.\\n\\n\"
            \"Slide Text:\\n\"
            f\"{slide_text}\\n\"
        )

        try:
            # Using structured outputs (available in latest OpenAI API)
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {\"role\": \"system\", \"content\": \"You are a helpful assistant designed to deeply understand lecture slides and extract structured outlines.\"},
                    {\"role\": \"user\", \"content\": prompt}
                ],
                response_format=SlideStructure,
                temperature=0.0
            )
            parsed_result = response.choices[0].message.parsed
            
            # Convert to list of dicts for portability
            return [t.model_dump() for t in parsed_result.topics]
            
        except Exception as e:
            print(f\"Error extracting structure from slides: {e}\")
            return []

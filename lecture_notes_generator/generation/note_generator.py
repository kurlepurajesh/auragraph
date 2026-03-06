import os
import re
from openai import OpenAI
from typing import List, Dict, Any

class NoteGenerator:
    def __init__(self, api_key: str = None, model: str = "gpt-4o"):
        """
        Initializes the Note Generator using LLM.
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key must be provided or set in OPENAI_API_KEY env var.")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def generate_topic_note(self, topic: str, key_points: List[str], textbook_chunks: List[Dict[str, Any]]) -> str:
        """
        Generates markdown notes for a SINGLE topic using the slide key points and textbook context.
        This feature works extensively to produce comprehensive, highly structured pedagogical material.
        """
        context_text = "\\n\\n---\\n\\n".join([chunk['text'] for chunk in textbook_chunks])
        
        system_prompt = (
            "You are an expert Professor and precise academic writer. Your goal is to generate "
            "comprehensive, structured lecture notes that synthesize lecture slides with textbook context.\\n"
            "You create study materials that are highly readable, pedagogically sound, and directly aligned "
            "with the lecture's scope.\\n"
        )

        key_points_formatted = "\\n".join([f"- {kp}" for kp in key_points])
        
        user_prompt = (
            f"Generate structured, high-quality lecture notes for the following topic.\\n\\n"
            f"--- INPUT ---\\n"
            f"Topic: {topic}\\n"
            f"Slide Key Points: \\n{key_points_formatted}\\n\\n"
            f"Textbook Context (Top Retrieved Excerpts):\\n{context_text}\\n\\n"
            f"--- INSTRUCTIONS ---\\n"
            f"1. **Scope Limit**: You MUST firmly anchor your notes to the 'Topic' and 'Slide Key Points'. "
            f"Do NOT introduce major new concepts from the textbook that are not strongly related to the slide points.\\n"
            f"2. **Textbook Usage**: Use the 'Textbook Context' to enrich the explanation. Explain the 'why' and 'how'. "
            f"Define any technical terms clearly.\\n"
            f"3. **Formatting & Structure**: Use Markdown. You MUST follow this exact structure:\\n"
            f"   - Start with an H2 (##) heading exactly matching the Topic name: {topic}\\n"
            f"   - **Overview**: An H3 (### Overview) followed by a 1-2 sentence high-level summary of what this topic is about.\\n"
            f"   - **Key Concepts**: Expand on each of the Slide Key Points in detail using textbook context. Use H4 (####) or bold bullet points for sub-concepts.\\n"
            f"   - **Examples/Applications** (if applicable): Provide a concrete example derived from the textbook context to illustrate the theory. If none exist in the context, you may omit this section.\\n"
            f"   - **Key Takeaways**: An H3 (### Key Takeaways) followed by a bulleted summary of the most critical exam-relevant facts.\\n"
            f"4. **Tone**: Objective, educational, academic yet accessible. Use bolding to emphasize keywords.\\n"
            f"5. **Missing Context**: If the textbook context does not contain relevant information for a specific key point, "
            f"explain the concept concisely based on general academic knowledge, but do not hallucinate specific textbook references.\\n"
        )

        # Fix actual string formatting by evaling the prompt text into standard string format
        # without raw escape sequences. Because of JSON-encoding literal \n vs \n
        system_prompt = system_prompt.replace("\\n", "\n")
        user_prompt = user_prompt.replace("\\n", "\n")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating note for topic '{topic}': {e}")
            return f"## {topic}\n\n[Error generating content: {e}]"

    def refine_notes(self, merged_notes: str) -> str:
        """
        Refines the merged document to ensure overarching flow, consistency, and professional formatting.
        """
        system_prompt = (
            "You are a meticulous professional editor specializing in academic textbooks and study guides."
        )

        user_prompt = (
            "Please review, refine, and polish the following merged lecture notes.\\n\\n"
            "--- INSTRUCTIONS ---\\n"
            "1. **Do NOT add new topics** or change the core structure/order of the headings.\\n"
            "2. **Enhance Readability**: Improve sentence flow, fix clumsy phrasing, and ensure a unified academic tone.\\n"
            "3. **Consistent Formatting**: Ensure Markdown is perfectly consistent (e.g., standardizing bullet points, bolding, and spacing).\\n"
            "4. **Formatting Upgrades**: If appropriate, you may format dense lists into Markdown tables to improve scannability, but DO NOT change the underlying information.\\n"
            "5. **Clean Output**: Return ONLY the refined Markdown text. Do not add conversational intro/outro text.\\n\\n"
            "--- NOTES TO REFINE ---\\n"
            f"{merged_notes}\\n"
        )
        
        user_prompt = user_prompt.replace("\\n", "\n")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error refining notes: {e}")
            return merged_notes

def merge_notes(topic_notes: List[str]) -> str:
    """
    Concatenates all topic notes in order and prepends a Table of Contents.
    """
    toc = ["# Table of Contents\n"]
    
    for note in topic_notes:
        # Extract the H2 heading (assume it's the first line starting with ##)
        match = re.search(r'^##\s+(.*)', note, re.MULTILINE)
        if match:
            heading = match.group(1).strip()
            # Create standard markdown anchor link
            anchor = heading.lower().replace(" ", "-")
            anchor = re.sub(r'[^a-z0-9-]', '', anchor)
            toc.append(f"- [{heading}](#{anchor})")
    
    toc_str = "\n".join(toc)
    notes_str = "\n\n---\n\n".join(topic_notes)
    
    # Combine everything with title and spacing
    return f"# Structured Lecture Notes\n\n{toc_str}\n\n---\n\n{notes_str}"

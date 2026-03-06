import os
import argparse
from typing import List, Dict, Any

from extract.pdf_parser import extract_slides, extract_textbook
from indexing.chunker import Chunker
from indexing.embedder import Embedder
from indexing.vector_db import VectorDB
from understanding.slide_analyzer import SlideAnalyzer
from retrieval.topic_retriever import TopicRetriever
from generation.note_generator import NoteGenerator, merge_notes

def main():
    parser = argparse.ArgumentParser(description=\"Lecture Slides -> Structured Notes Generator\")
    parser.add_argument(\"--slides\", required=True, help=\"Path to the lecture slides (PDF or PPTX)\")
    parser.add_argument(\"--textbook\", required=True, help=\"Path to the reference textbook (PDF)\")
    parser.add_argument(\"--output\", default=\"final_notes.md\", help=\"Path to the output Markdown file\")
    args = parser.parse_args()

    print(\"\\n=== Lecture Notes Generator ===\\n\")

    # 1. Initialization
    print(\"[1/8] Initializing models and databases...\")
    try:
        chunker = Chunker(chunk_size_words=400, overlap_words=50)
        embedder = Embedder(model_name=\"all-MiniLM-L6-v2\")
        
        # Determine embedding dimension from a dummy text
        dummy_embedding = embedder.embed_texts([\"dummy\"])[0]
        dimension = dummy_embedding.shape[0]
        vector_db = VectorDB(embedding_dim=dimension)
        
        slide_analyzer = SlideAnalyzer(model=\"gpt-4o\")
        topic_retriever = TopicRetriever(embedder=embedder, vector_db=vector_db)
        note_generator = NoteGenerator(model=\"gpt-4o\")
    except Exception as e:
        print(f\"Initialization Error: {e}\")
        print(\"Please ensure OPENAI_API_KEY is set in your environment.\")
        return

    # 2. Text Extraction
    print(\"[2/8] Extracting text from slides and textbook...\")
    slide_text = extract_slides(args.slides)
    textbook_text = extract_textbook(args.textbook)

    print(f\"      Slide length: {len(slide_text)} chars\")
    print(f\"      Textbook length: {len(textbook_text)} chars\")

    # 3. Textbook Chunking
    print(\"[3/8] Chunking textbook...\")
    chunks = chunker.chunk_text(textbook_text)
    print(f\"      Generated {len(chunks)} chunks.\")

    # 4. Create Embeddings & Indexing
    print(\"[4/8] Generating embeddings and indexing...\")
    if chunks:
        texts = [chunk[\"text\"] for chunk in chunks]
        embeddings = embedder.embed_texts(texts)
        for i, chunk in enumerate(chunks):
            chunk[\"embedding\"] = embeddings[i]
        
        vector_db.add_chunks(chunks)

    # 5. Slide Understanding
    print(\"[5/8] Analyzing slide structure using LLM...\")
    slide_structure_list = slide_analyzer.extract_structure(slide_text)
    
    if not slide_structure_list:
        print(\"Error: Failed to extract slide structure.\")
        return
        
    print(f\"      Found {len(slide_structure_list)} topics.\")

    # 6. Topic-Based Retrieval & Topic-wise Note Generation
    print(\"[6/8] Retrieving context and generating notes per topic...\")
    topic_notes = []
    
    for i, topic_data in enumerate(slide_structure_list):
        topic_name = topic_data.get(\"topic\", \"Unknown Topic\")
        print(f\"      -> Processing Topic {i+1}/{len(slide_structure_list)}: {topic_name}\")
        
        # Retrieval
        retrieved_chunks = topic_retriever.retrieve_for_topic(topic_data, top_k=5)
        
        # Generation
        note = note_generator.generate_topic_note(
            topic=topic_name,
            key_points=topic_data.get(\"key_points\", []),
            textbook_chunks=retrieved_chunks
        )
        topic_notes.append(note)

    # 7. Merge Notes
    print(\"[7/8] Merging notes...\")
    merged_notes = merge_notes(topic_notes)

    # 8. Refinement
    print(\"[8/8] Refining final document using LLM...\")
    final_notes = note_generator.refine_notes(merged_notes)

    # 9. Save to output
    try:
        with open(args.output, \"w\", encoding=\"utf-8\") as f:
            f.write(final_notes)
        print(f\"\\nSuccess! Notes saved to '{args.output}'.\")
    except Exception as e:
        print(f\"Error saving notes: {e}\")

if __name__ == \"__main__\":
    main()

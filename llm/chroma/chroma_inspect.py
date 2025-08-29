# llm/chroma/chroma_inspect.py

import os
import chromadb
from pprint import pprint

CHROMA_COLLECTION = "moodle_documents"

def show_chroma_collection() -> None:
    host = os.getenv("CHROMA_HOST")
    port = int(os.getenv("CHROMA_PORT"))

    client = chromadb.HttpClient(host=host, port=port, ssl=False)
    collection = client.get_or_create_collection(name=CHROMA_COLLECTION)

    # Korrigiertes include (ohne "ids")
    query = collection.get(include=["documents", "metadatas"])

    if not query["ids"]:
        print(" Die Chroma-Collection ist leer.")
        return

    print(f" {len(query['ids'])} Dokumente in Collection '{CHROMA_COLLECTION}':\n")
    for idx, (doc, meta, _id) in enumerate(zip(query["documents"], query["metadatas"], query["ids"]), 1):
        print(f"---  Dokument {idx} ---")
        print(f" ID: {_id}")
        print(f" Metadaten:")
        pprint(meta, indent=4)
        print(" Inhalt:")
        print(doc[:3000].strip() + "...\n")
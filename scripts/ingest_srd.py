"""One-off ingestion of the SRD markdown corpus into the sqlite-vec table.

Run once per corpus change:
    poetry run python scripts/ingest_srd.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from agent.tools.srd_rules_retriever import vectorstore
from settings.settings import settings


def main() -> int:
    rules_dir = settings.BASE_PATH / "data" / "rules"
    loader = DirectoryLoader(str(rules_dir), glob="**/*.md", loader_cls=TextLoader)
    docs = loader.load()

    headers_to_split_on = [("#", "h1"), ("##", "h2"), ("###", "h3")]
    md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_docs = []
    for doc in docs:
        md_docs.extend(md_splitter.split_text(doc.page_content))

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        length_function=len,
    )
    chunks = text_splitter.split_documents(md_docs)

    vectorstore.add_documents(chunks)
    print(f"Ingested {len(chunks)} chunks from {len(docs)} source file(s) into rules_srd_splitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import sqlite3

import sqlite_vec
from langchain_community.vectorstores import sqlitevec
from langchain_core.tools import create_retriever_tool
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from db.core import DB_PATH


def _open_vec_connection(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2-preview")

vectorstore = sqlitevec.SQLiteVec(
    table="rules_srd_splitted",
    db_file=str(DB_PATH),
    embedding=embeddings,
    connection=_open_vec_connection(str(DB_PATH)),
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

rules_srd_retriever = create_retriever_tool(
    retriever=retriever,
    name="rules_srd_retriever",
    description="Search the D&D 5e SRD for rules, spells, class features, conditions, combat mechanics, etc.",
)

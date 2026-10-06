from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_openai import OpenAIEmbeddings 
from langchain_community.vectorstores import sqlitevec
from settings.settings import settings
from langchain_core.tools import create_retriever_tool

loader = DirectoryLoader(str(settings.BASE_PATH)+"/data/rules", glob="**/*.md", loader_cls=TextLoader)
docs = loader.load()

headers_to_split_on = [("#", "h1"), ("##", "h2"), ("###", "h3")]
md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
md_docs = []
for doc in docs:
    md_docs.extend(md_splitter.split_text(doc.page_content))

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    length_function=len
)
chunks = text_splitter.split_documents(md_docs)

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = sqlitevec.SQLiteVec(
table="rules_srd_splitted",
db_file=str(settings.BASE_PATH),
embedding=embeddings,
connection=None
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

rules_srd_retriever = create_retriever_tool(retriever=retriever, name = "rules_srd_retriever", description="Search the D&D 5e SRD for rules, spells, class features, conditions, combat mechanics, etc.")
import os
# 放在文件最开头！！
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from sentence_transformers import SentenceTransformer
import faiss
import numpy as np



class RuleRAG:
    def __init__(self, rule_file_path: str, model_name="all-MiniLM-L6-v2"):
        # 加载Embedding模型
        self.emb_model = SentenceTransformer(model_name)
        # 读取规则文档
        with open(rule_file_path, "r", encoding="utf-8") as f:
            full_text = f.read()

        # NLP滑动窗口分块
        chunk_size = 300
        step = 150
        self.chunks = []
        for i in range(0, len(full_text), step):
            chunk = full_text[i:i + chunk_size]
            self.chunks.append(chunk)

        # 向量化
        embeddings = self.emb_model.encode(self.chunks, normalize_embeddings=True)
        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(np.array(embeddings).astype(np.float32))

    def retrieve_rule(self, query: str, top_k=3) -> str:
        q_emb = self.emb_model.encode([query], normalize_embeddings=True)
        q_emb = np.array(q_emb).astype(np.float32)
        scores, idx = self.index.search(q_emb, top_k)
        retrieved = "\n---\n".join([self.chunks[i] for i in idx[0]])
        return retrieved

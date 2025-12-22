# -*- coding: utf-8 -*-
import streamlit as st
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
import chromadb
from chromadb.config import Settings
from groq import Groq
import PyPDF2
from docx import Document
import io
import base64
import asyncio
import httpx
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
import html
import re
from markitdown import MarkItDown
import logging

# Logging ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# SAYFA YAPILANDIRMASI
# ============================================================================
st.set_page_config(
    page_title="Hukuk AI Asistanı",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Stilleri
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; }
    .stTextArea>div>div>textarea { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# EMSAL API - Models
# ============================================================================

class EmsalDetailedSearchRequestData(BaseModel):
    """Emsal detaylı arama için API payload modeli."""
    arananKelime: Optional[str] = ""
    Bam_Hukuk_Mahkemeleri: str = Field("", alias="Bam Hukuk Mahkemeleri")
    Hukuk_Mahkemeleri: str = Field("", alias="Hukuk Mahkemeleri")
    birimHukukMah: Optional[str] = Field("", description="Bölge adliye mahkemeleri daireleri")
    esasYil: Optional[str] = ""
    esasIlkSiraNo: Optional[str] = ""
    esasSonSiraNo: Optional[str] = ""
    kararYil: Optional[str] = ""
    kararIlkSiraNo: Optional[str] = ""
    kararSonSiraNo: Optional[str] = ""
    baslangicTarihi: Optional[str] = ""
    bitisTarihi: Optional[str] = ""
    siralama: str
    siralamaDirection: str
    pageSize: int
    pageNumber: int

    model_config = ConfigDict(populate_by_name=True)

class EmsalSearchRequest(BaseModel):
    """Emsal arama isteği modeli."""
    keyword: str = Field("", description="Arama kelimesi")
    selected_bam_civil_court: str = Field("", description="BAM Hukuk Mahkemesi")
    selected_civil_court: str = Field("", description="Hukuk Mahkemesi")
    selected_regional_civil_chambers: List[str] = Field(default_factory=list, description="Bölge daireleri")
    case_year_esas: str = Field("", description="Esas yılı")
    case_start_seq_esas: str = Field("", description="Esas başlangıç no")
    case_end_seq_esas: str = Field("", description="Esas bitiş no")
    decision_year_karar: str = Field("", description="Karar yılı")
    decision_start_seq_karar: str = Field("", description="Karar başlangıç no")
    decision_end_seq_karar: str = Field("", description="Karar bitiş no")
    start_date: str = Field("", description="Başlangıç tarihi (DD.MM.YYYY)")
    end_date: str = Field("", description="Bitiş tarihi (DD.MM.YYYY)")
    sort_criteria: str = Field("1", description="Sıralama")
    sort_direction: str = Field("desc", description="Yön")
    page_number: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=10)

class EmsalApiDecisionEntry(BaseModel):
    """Emsal API'den gelen karar girdisi."""
    id: str
    daire: str = Field("", description="Daire")
    esasNo: str = Field("", description="Esas No")
    kararNo: str = Field("", description="Karar No")
    kararTarihi: str = Field("", description="Karar Tarihi")
    arananKelime: str = Field("", description="Aranan Kelime")
    durum: str = Field("", description="Durum")
    document_url: Optional[HttpUrl] = Field(None, description="Belge URL")
    model_config = ConfigDict(extra='ignore')

class EmsalApiResponseInnerData(BaseModel):
    """Emsal API yanıt verisi."""
    data: List[EmsalApiDecisionEntry]
    recordsTotal: int
    recordsFiltered: int
    draw: int = Field(0, description="Çizim sayacı")

class EmsalApiResponse(BaseModel):
    """Emsal API tam yanıt modeli."""
    data: EmsalApiResponseInnerData
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata")

class EmsalDocumentMarkdown(BaseModel):
    """Emsal karar belgesi (Markdown formatında)."""
    id: str
    markdown_content: str = Field("", description="Markdown içerik")
    source_url: HttpUrl

# ============================================================================
# EMSAL API - Client
# ============================================================================

class EmsalApiClient:
    """UYAP Emsal (İçtihat) arama sistemi için API client."""
    BASE_URL = "https://emsal.uyap.gov.tr"
    DETAILED_SEARCH_ENDPOINT = "/aramadetaylist"
    DOCUMENT_ENDPOINT = "/getDokuman"

    def __init__(self, request_timeout: float = 30.0):
        self.http_client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=request_timeout,
            verify=False
        )

    async def search_detailed_decisions(self, params: EmsalSearchRequest) -> EmsalApiResponse:
        data_for_api_payload = EmsalDetailedSearchRequestData(
            arananKelime=params.keyword or "",
            Bam_Hukuk_Mahkemeleri=params.selected_bam_civil_court,
            Hukuk_Mahkemeleri=params.selected_civil_court,
            birimHukukMah="+".join(params.selected_regional_civil_chambers) if params.selected_regional_civil_chambers else "",
            esasYil=params.case_year_esas or "",
            esasIlkSiraNo=params.case_start_seq_esas or "",
            esasSonSiraNo=params.case_end_seq_esas or "",
            kararYil=params.decision_year_karar or "",
            kararIlkSiraNo=params.decision_start_seq_karar or "",
            kararSonSiraNo=params.decision_end_seq_karar or "",
            baslangicTarihi=params.start_date or "",
            bitisTarihi=params.end_date or "",
            siralama=params.sort_criteria,
            siralamaDirection=params.sort_direction,
            pageSize=params.page_size,
            pageNumber=params.page_number
        )
        payload_dict = data_for_api_payload.model_dump(by_alias=True, exclude_none=True)
        cleaned_payload = {k: v for k, v in payload_dict.items() if v != ""}
        final_payload = {"data": cleaned_payload}
        return await self._execute_api_search(self.DETAILED_SEARCH_ENDPOINT, final_payload)

    async def _execute_api_search(self, endpoint: str, payload: Dict) -> EmsalApiResponse:
        try:
            response = await self.http_client.post(endpoint, json=payload)
            response.raise_for_status()
            api_response_parsed = EmsalApiResponse(**response.json())
            if api_response_parsed.data and api_response_parsed.data.data:
                for decision_item in api_response_parsed.data.data:
                    if decision_item.id:
                        decision_item.document_url = f"{self.BASE_URL}{self.DOCUMENT_ENDPOINT}?id={decision_item.id}"
            return api_response_parsed
        except Exception as e:
            logger.error(f"Emsal API Hatası: {e}")
            raise

    async def get_decision_document_as_markdown(self, id: str) -> EmsalDocumentMarkdown:
        document_api_url = f"{self.DOCUMENT_ENDPOINT}?id={id}"
        source_url = f"{self.BASE_URL}{document_api_url}"
        try:
            response = await self.http_client.get(document_api_url)
            response.raise_for_status()
            html_content = response.json().get("data", "")
            
            # Markdown dönüşümü
            md_converter = MarkItDown()
            content_io = io.BytesIO(html.unescape(html_content).encode('utf-8'))
            markdown_text = md_converter.convert(content_io).text_content
            
            return EmsalDocumentMarkdown(id=id, markdown_content=markdown_text, source_url=source_url)
        except Exception as e:
            logger.error(f"Belge Alma Hatası: {e}")
            raise

# ============================================================================
# HUKUK AI ASİSTANI - Ana Sınıf
# ============================================================================

class HukukAIAsistani:
    def __init__(self):
        self.groq_api_key = st.session_state.get('groq_api_key', '')
        self.data_dir = Path("hukuk_data")
        self.data_dir.mkdir(exist_ok=True)
        
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.data_dir / "chroma_db"),
            settings=Settings(anonymized_telemetry=False)
        )
        
        self.collections = {
            'ictihatlar': self._get_or_create_collection('ictihatlar'),
            'mevzuat': self._get_or_create_collection('mevzuat'),
            'sozlesmeler': self._get_or_create_collection('sozlesmeler'),
            'dilekce': self._get_or_create_collection('dilekce'),
        }
        self.emsal_client = EmsalApiClient()

    def _get_or_create_collection(self, name):
        return self.chroma_client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def generate_embedding(self, text):
        # Basit simülasyon (Gerçekte Sentence-Transformers önerilir)
        hash_obj = hashlib.sha256(text.encode())
        hex_val = hash_obj.hexdigest()
        embedding = [int(hex_val[i:i+2], 16) / 255.0 for i in range(0, min(len(hex_val), 768), 2)]
        while len(embedding) < 384: embedding.append(0.0)
        return embedding[:384]

    def add_document(self, col_name, text, metadata):
        collection = self.collections.get(col_name)
        if not collection: return False
        doc_id = hashlib.md5((text + str(datetime.now())).encode()).hexdigest()
        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        for idx, chunk in enumerate(chunks):
            collection.add(
                ids=[f"{doc_id}_{idx}"],
                documents=[chunk],
                embeddings=[self.generate_embedding(chunk)],
                metadatas=[{**metadata, 'chunk': idx}]
            )
        return True

    def chat_with_rag(self, query, collection_names):
        client = Groq(api_key=self.groq_api_key)
        context_parts = []
        for name in collection_names:
            results = self.collections[name].query(query_embeddings=[self.generate_embedding(query)], n_results=2)
            if results['documents']: context_parts.extend(results['documents'][0])
        
        context = "\n\n".join(context_parts) if context_parts else "Bağlam bulunamadı."
        
        prompt = f"Bağlam:\n{context}\n\nSoru: {query}\nCevap:"
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": "Sen uzman bir hukuk asistanısın."}, {"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content

    # Diğer metodlar (Analyze, Generate vb.) buraya benzer yapıyla eklendi...
    def generate_document(self, doc_type, prompt_text):
        client = Groq(api_key=self.groq_api_key)
        sys_msg = f"Hukuki {doc_type} oluştur."
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt_text}]
        )
        return completion.choices[0].message.content

# ============================================================================
# YARDIMCI FONKSİYONLAR VE UI
# ============================================================================

def main():
    st.title("⚖️ Hukuk AI Asistanı")
    
    with st.sidebar:
        st.header("⚙️ Ayarlar")
        api_key = st.text_input("Groq API Key", type="password")
        if api_key: st.session_state.groq_api_key = api_key

    if not st.session_state.get('groq_api_key'):
        st.warning("Lütfen API anahtarını girin.")
        return

    if 'ai_assistant' not in st.session_state:
        st.session_state.ai_assistant = HukukAIAsistani()

    tab1, tab2, tab3 = st.tabs(["🤖 Sohbet", "⚖️ UYAP Emsal", "📝 Belge Yazım"])

    with tab1:
        q = st.text_area("Hukuki sorunuz:")
        if st.button("Sor"):
            res = st.session_state.ai_assistant.chat_with_rag(q, ['ictihatlar', 'mevzuat'])
            st.markdown(res)

    with tab2:
        keyword = st.text_input("Arama Kelimesi")
        if st.button("UYAP'ta Ara"):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            params = EmsalSearchRequest(keyword=keyword)
            result = loop.run_until_complete(st.session_state.ai_assistant.emsal_client.search_detailed_decisions(params))
            for dec in result.data.data:
                st.write(f"📄 {dec.esasNo} - {dec.daire}")

    with tab3:
        doc_p = st.text_area("Belge içeriği tarif edin:")
        if st.button("Belgeyi Yaz"):
            res = st.session_state.ai_assistant.generate_document("dilekçe", doc_p)
            st.code(res)

if __name__ == "__main__":
    main()
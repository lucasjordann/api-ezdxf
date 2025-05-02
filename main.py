from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf
import requests
import os
import base64
import re
import json
from datetime import datetime
import pytz
from typing import Optional, List

app = FastAPI()

# ─── Health check ────────────────────────────────────────────────────────────
@app.get("/")
def health_check():
    return {"status": "ok"}

# ─── Configurações ──────────────────────────────────────────────────────────
GITHUB_REPO    = "lucasjordann/api-ezdxf"
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
KNOWLEDGE_PATH = "knowledge.jsonl"

# ─── Modelos Pydantic ────────────────────────────────────────────────────────
class DXFUrlRequest(BaseModel):
    file_url: str
    instrucoes: Optional[str] = None

class ExecutarComandoRequest(BaseModel):
    file_url: str
    comando: str

class Acao(BaseModel):
    tipo: str
    nome: Optional[str] = None
    cor: Optional[int] = None
    inicio: Optional[List[float]] = None
    fim: Optional[List[float]] = None
    layer: Optional[str] = None
    vertices: Optional[List[List[float]]] = None
    centro: Optional[List[float]] = None
    raio: Optional[float] = None
    angulo_inicio: Optional[float] = None
    angulo_fim: Optional[float] = None
    major_axis: Optional[List[float]] = None
    minor_radius: Optional[float] = None
    major_radius: Optional[float] = None
    canto1: Optional[List[float]] = None
    canto2: Optional[List[float]] = None
    local: Optional[List[float]] = None
    direcao: Optional[List[float]] = None
    pontos: Optional[List[List[float]]] = None
    inner_radius: Optional[float] = None
    outer_radius: Optional[float] = None
    corners: Optional[List[List[float]]] = None
    base: Optional[List[float]] = None
    height: Optional[float] = None
    turns: Optional[int] = None
    contorno: Optional[List[List[float]]] = None
    tag: Optional[str] = None
    prompt: Optional[str] = None
    insert: Optional[List[float]] = None
    distance: Optional[float] = None

class ExecutarAcoesRequest(BaseModel):
    file_url: str
    acoes: List[Acao]

# ─── Registrar aprendizado ──────────────────────────────────────────────────
def registrar_aprendizado(comando: str, detalhes: str):
    br_tz = pytz.timezone("America/Sao_Paulo")
    registro = {
        "comando": comando,
        "detalhes": detalhes,
        "timestamp": datetime.now(br_tz).strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(KNOWLEDGE_PATH, "a") as f:
        f.write(json.dumps(registro) + "\n")

# ─── Funções CAD básicas ────────────────────────────────────────────────────
def explodir_blocos(msp):
    count = 0
    for ent in list(msp):
        if ent.dxftype() == "INSERT":
            try:
                for o in ent.explode():
                    msp.add_entity(o)
                msp.delete_entity(ent)
                count += 1
            except Exception:
                pass
    return count

def mudar_cor_todos(msp, cor: int = 7):
    alterados = 0
    for ent in msp:
        if hasattr(ent.dxf, "color"):
            ent.dxf.color = cor
            alterados += 1
    return alterados

# ─── Endpoint 1: instruções livres ───────────────────────────────────────────
@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)

    ts = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y%m%d_%H%M%S")
    filename   = f"saida_{ts}.dxf"
    orig_path  = os.path.join(temp_dir, "baixado.dxf")
    dest_path  = os.path.join(temp_dir, filename)
    github_api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    raw_url    = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"

    # Download
    resp = requests.get(data.file_url)
    if resp.status_code != 200:
        return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: {resp.status_code}"})
    with open(orig_path, "wb") as f:
        f.write(resp.content)

    # Abrir e modificar
    try:
        doc = ezdxf.readfile(orig_path)
        msp = doc.modelspace()
        msp.add_text("Texto via API", dxfattribs={"insert": (100, 100)})

        if data.instrucoes:
            txt = data.instrucoes.lower()
            if "explodir blocos" in txt:
                n = explodir_blocos(msp)
                registrar_aprendizado("explodir blocos", f"{n} blocos explodidos")
            m = re.search(r"cor de todos(?: os itens| os objetos)? para (\d+)", txt)
            if m:
                c = int(m.group(1))
                n = mudar_cor_todos(msp, c)
                registrar_aprendizado(f"mudar cor de todos os itens para {c}", f"{n} entidades alteradas")

        doc.saveas(dest_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao processar DXF: {str(e)}"})

    # Upload GitHub
    with open(dest_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    put = requests.put(
        github_api,
        json={"message": f"upload {filename}", "content": content_b64, "branch": "main"},
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"}
    )
    if put.status_code not in (200, 201):
        return JSONResponse(status_code=500, content={"error": "Falha no upload", "detalhes": put.json()})

    return JSONResponse(content={"mensagem": "Arquivo modificado com sucesso", "download_url": raw_url})

# ─── Endpoint 2: comando aprendido ───────────────────────────────────────────
@app.post("/executar_comando/")
def executar_comando(data: ExecutarComandoRequest):
    if not data.file_url or not data.comando:
        return JSONResponse(status_code=400, content={"error": "'file_url' e 'comando' obrigatórios"})

    etapas = []
    if os.path.exists(KNOWLEDGE_PATH):
        with open(KNOWLEDGE_PATH) as f:
            for linha in f:
                reg = json.loads(linha)
                if reg.get("comando") == data.comando and reg.get("etapas"):
                    etapas = reg["etapas"]
                    break
    if not etapas:
        return JSONResponse(status_code=404, content={"error": f"Comando '{data.comando}' não encontrado"})

    instr = ", ".join(etapas)
    return modificar_dxf_url(DXFUrlRequest(file_url=data.file_url, instrucoes=instr))

# ─── Endpoint 3: ações CAD detalhadas ────────────────────────────────────────
@app.post("/executar_acoes/")
def executar_acoes(data: ExecutarAcoesRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)

    ts = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y%m%d_%H%M%S")
    filename   = f"saida_{ts}.dxf"
    orig_path  = os.path.join(temp_dir, "baixado.dxf")
    dest_path  = os.path.join(temp_dir, filename)
    github_api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    raw_url    = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"

    # Download
    resp = requests.get(data.file_url)
    if resp.status_code != 200:
        return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: {resp.status_code}"})
    with open(orig_path, "wb") as f:
        f.write(resp.content)

    # Abrir DXF
    try:
        doc = ezdxf.readfile(orig_path)
        msp = doc.modelspace()

        # Executar ações
        for ac in data.acoes:
            tipo = ac.tipo.lower()

            if tipo == "criar_layer" and ac.nome:
                if ac.nome not in doc.layers:
                    doc.layers.new(name=ac.nome, dxfattribs={"color": ac.cor or 7})
                    msp.add_point((0, 0), dxfattribs={"layer": ac.nome})

            elif tipo in ("line", "desenhar_linha") and ac.inicio and ac.fim:
                msp.add_line(tuple(ac.inicio), tuple(ac.fim), dxfattribs={"layer": ac.layer or "0"})

            elif tipo in ("circle", "desenhar_circulo") and ac.centro and ac.raio is not None:
                msp.add_circle(tuple(ac.centro), ac.raio, dxfattribs={"layer": ac.layer or "0"})

            # … outros tipos de entidades conforme necessário …

        doc.saveas(dest_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Erro ao processar ações", "detalhes": str(e)})

    # Upload
    with open(dest_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    put = requests.put(
        github_api,
        json={"message": f"upload {filename}", "content": content_b64, "branch": "main"},
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                 "Accept": "application/vnd.github.v3+json"}
    )
    if put.status_code not in (200, 201):
        return JSONResponse(status_code=500, content={"error": "Falha no upload", "detalhes": put.json()})

    return JSONResponse(content={"mensagem": "Arquivo modificado com sucesso", "download_url": raw_url})

# ─── Run local (opcional) ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)

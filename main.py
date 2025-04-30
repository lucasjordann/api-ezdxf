from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf, requests, os, base64, re, json
from datetime import datetime
import pytz
from typing import Optional, List

app = FastAPI()

GITHUB_REPO = "lucasjordann/api-ezdxf"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
KNOWLEDGE_PATH = "knowledge.jsonl"

class Acao(BaseModel):
    tipo: str
    nome: Optional[str] = None
    cor: Optional[int] = None
    inicio: Optional[List[float]] = None
    fim: Optional[List[float]] = None
    layer: Optional[str] = None

class DXFAcaoRequest(BaseModel):
    file_url: str
    acoes: List[Acao]

class DXFUrlRequest(BaseModel):
    file_url: str
    instrucoes: Optional[str] = None

def registrar_aprendizado(comando: str, detalhes: str):
    br_tz = pytz.timezone("America/Sao_Paulo")
    registro = {
        "comando": comando,
        "detalhes": detalhes,
        "timestamp": datetime.now(br_tz).strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(KNOWLEDGE_PATH, "a") as f:
        f.write(json.dumps(registro) + "\n")

def explodir_blocos(msp):
    blocos_explodidos = 0
    for entidade in list(msp):
        if entidade.dxftype() == "INSERT":
            try:
                entidades_explodidas = entidade.explode()
                for nova in entidades_explodidas:
                    msp.add_entity(nova)
                msp.delete_entity(entidade)
                blocos_explodidos += 1
            except Exception:
                continue
    return blocos_explodidos

def mudar_cor_todos(msp, cor: int = 7):
    alterados = 0
    for e in msp:
        if hasattr(e.dxf, "color"):
            e.dxf.color = cor
            alterados += 1
    return alterados

def executar_acoes(doc, msp, acoes: List[Acao]):
    for acao in acoes:
        if acao.tipo == "criar_layer" and acao.nome:
            if acao.nome not in doc.layers:
                doc.layers.new(name=acao.nome, dxfattribs={"color": acao.cor or 7})
                # Registrar layer criadacom um ponto mínimo para garantir visibilidade
                msp.add_point((0, 0), dxfattribs={"layer": acao.nome})
        elif acao.tipo == "desenhar_linha" and acao.inicio and acao.fim:
            msp.add_line(acao.inicio, acao.fim, dxfattribs={"layer": acao.layer or "0"})
        elif acao.tipo == "excluir_por_layer" and acao.layer:
            for e in list(msp):
                if e.dxf.layer == acao.layer:
                    msp.delete_entity(e)

@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)

    br_tz = pytz.timezone("America/Sao_Paulo")
    timestamp = datetime.now(br_tz).strftime("%Y%m%d_%H%M%S")
    filename = f"saida_{timestamp}.dxf"

    original_path = os.path.join(temp_dir, "baixado.dxf")
    modified_path = os.path.join(temp_dir, filename)
    github_api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"

    try:
        response = requests.get(data.file_url)
        if response.status_code != 200:
            return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: status {response.status_code}"})
        with open(original_path, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Falha ao baixar arquivo: {str(e)}"})

    try:
        doc = ezdxf.readfile(original_path)
        msp = doc.modelspace()
        msp.add_text("Texto via API", dxfattribs={"insert": (100, 100)})

        if data.instrucoes:
            texto = data.instrucoes.lower()
            if "explodir blocos" in texto:
                total = explodir_blocos(msp)
                registrar_aprendizado("explodir blocos", f"{total} blocos explodidos")
            match_cor = re.search(r"cor de todos(?: os itens| os objetos)? para (\d+)", texto)
            if match_cor:
                cor = int(match_cor.group(1))
                total = mudar_cor_todos(msp, cor)
                registrar_aprendizado(f"mudar cor de todos os itens para {cor}", f"{total} entidades alteradas")
        doc.saveas(modified_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao processar DXF: {str(e)}"})

    try:
        with open(modified_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        payload = {"message": f"upload {filename}", "content": content_b64, "branch": "main"}
        put_resp = requests.put(github_api_url, json=payload, headers=headers)
        if put_resp.status_code not in [200, 201]:
            return JSONResponse(status_code=500, content={"error": "Erro ao fazer upload para GitHub", "detalhes": put_resp.json()})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro durante upload: {str(e)}"})

    return JSONResponse(content={"mensagem": "Arquivo modificado com sucesso", "download_url": raw_url})

@app.post("/executar_comando/")
def executar_comando(data: dict):
    file_url = data.get("file_url")
    comando = data.get("comando")
    if not file_url or not comando:
        return JSONResponse(status_code=400, content={"error": "Campos 'file_url' e 'comando' são obrigatórios."})
    etapas = []
    if os.path.exists(KNOWLEDGE_PATH):
        with open(KNOWLEDGE_PATH, "r") as f:
            for linha in f:
                registro = json.loads(linha)
                if registro.get("comando") == comando and registro.get("detalhes"):
                    etapas = registro.get("detalhes") if isinstance(registro.get("detalhes"), list) else []
                    break
    if not etapas:
        return JSONResponse(status_code=404, content={"error": f"Comando '{comando}' ainda não tem etapas definidas."})
    instrucoes_txt = ", ".join(etapas)
    return modificar_dxf_url(DXFUrlRequest(file_url=file_url, instrucoes=instrucoes_txt))

@app.post("/executar_acoes/")
def executar_acoes_dxf(data: DXFAcaoRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)
    br_tz = pytz.timezone("America/Sao_Paulo")
    timestamp = datetime.now(br_tz).strftime("%Y%m%d_%H%M%S")
    filename = f"saida_{timestamp}.dxf"
    original_path = os.path.join(temp_dir, "baixado.dxf")
    modified_path = os.path.join(temp_dir, filename)
    github_api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"
    try:
        response = requests.get(data.file_url)
        if response.status_code != 200:
            return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: status {response.status_code}"})
        with open(original_path, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Falha ao baixar arquivo: {str(e)}"})
    try:
        doc = ezdxf.readfile(original_path)
        msp = doc.modelspace()
        executar_acoes(doc, msp, data.acoes)
        doc.saveas(modified_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao modificar DXF: {str(e)}"})
    try:
        with open(modified_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        payload = {"message": f"upload {filename}", "content": content_b64, "branch": "main"}
        put_resp = requests.put(github_api_url, json=payload, headers=headers)
        if put_resp.status_code not in [200, 201]:
            return JSONResponse(status_code=500, content={"error": "Erro ao fazer upload para GitHub", "detalhes": put_resp.json()})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro durante upload: {str(e)}"})
    return JSONResponse(content={"mensagem": "Arquivo modificado com sucesso", "download_url": raw_url})

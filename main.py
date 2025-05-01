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
    corners: Optional[List[List[float]]] = None
    inner_radius: Optional[float] = None
    outer_radius: Optional[float] = None
    pontos: Optional[List[List[float]]] = None
    tag: Optional[str] = None
    prompt: Optional[str] = None
    insert: Optional[List[float]] = None
    distance: Optional[float] = None
    dx: Optional[float] = None
    dy: Optional[float] = None
    angle: Optional[float] = None
    center: Optional[List[float]] = None
    scale_x: Optional[float] = None
    scale_y: Optional[float] = None

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
    from ezdxf.math import mirror_matrix, Matrix44

    for acao in acoes:
        tipo = acao.tipo.lower()
        # Layers
        if tipo == "criar_layer" and acao.nome:
            if acao.nome not in doc.layers:
                doc.layers.new(name=acao.nome, dxfattribs={"color": acao.cor or 7})
                msp.add_point((0, 0), dxfattribs={"layer": acao.nome})
        # Entidades Básicas
        elif tipo in ("line", "desenhar_linha") and acao.inicio and acao.fim:
            msp.add_line(tuple(acao.inicio), tuple(acao.fim), dxfattribs={"layer": acao.layer})
        elif tipo in ("pline", "polylinha") and acao.vertices:
            msp.add_lwpolyline([tuple(v) for v in acao.vertices], dxfattribs={"layer": acao.layer})
        elif tipo in ("circle", "desenhar_circulo") and acao.centro and acao.raio is not None:
            msp.add_circle(tuple(acao.centro), acao.raio, dxfattribs={"layer": acao.layer})
        elif tipo in ("arc", "desenhar_arco") and acao.centro and acao.raio is not None:
            msp.add_arc(tuple(acao.centro), acao.raio,
                        acao.angulo_inicio or 0, acao.angulo_fim or 360,
                        dxfattribs={"layer": acao.layer})
        elif tipo in ("ellipse", "desenhar_elipse") and acao.centro and acao.major_axis:
            ratio = (acao.minor_radius or 0) / (acao.major_radius or 1)
            msp.add_ellipse(center=tuple(acao.centro),
                            major_axis=tuple(acao.major_axis),
                            ratio=ratio,
                            dxfattribs={"layer": acao.layer})
        elif tipo in ("rectangle", "desenhar_retangulo") and acao.canto1 and acao.canto2:
            x1,y1 = acao.canto1; x2,y2 = acao.canto2
            pts = [(x1,y1),(x2,y1),(x2,y2),(x1,y2),(x1,y1)]
            msp.add_lwpolyline(pts, dxfattribs={"layer": acao.layer})
        elif tipo in ("point", "desenhar_ponto") and acao.local:
            msp.add_point(tuple(acao.local), dxfattribs={"layer": acao.layer})
        elif tipo == "ray" and acao.inicio and acao.direcao:
            msp.add_ray(tuple(acao.inicio), tuple(acao.direcao), dxfattribs={"layer": acao.layer})
        elif tipo == "xline" and acao.inicio and acao.direcao:
            msp.add_xline(tuple(acao.inicio), tuple(acao.direcao), dxfattribs={"layer": acao.layer})
        elif tipo in ("mline", "multiline") and acao.vertices:
            msp.add_mline([tuple(v) for v in acao.vertices], override={"color": acao.cor or 7})
        # Entidades Avançadas
        elif tipo == "spline" and acao.pontos:
            msp.add_spline(control_points=[tuple(p) for p in acao.pontos], dxfattribs={"layer": acao.layer})
        elif tipo == "hatch" and acao.vertices:
            hatch = msp.add_hatch(color=acao.cor or 7)
            hatch.paths.add_polyline_path([tuple(v) for v in acao.vertices], is_closed=True)
        elif tipo == "region" and acao.vertices:
            region = doc.entities.new("REGION")
            region.append_polygon([tuple(v) for v in acao.vertices])
        elif tipo == "donut" and acao.inner_radius is not None and acao.outer_radius is not None:
            msp.add_donut(acao.inner_radius, acao.outer_radius, dxfattribs={"layer": acao.layer})
        elif tipo == "solid" and acao.vertices:
            msp.add_solid([tuple(v) for v in acao.vertices], dxfattribs={"layer": acao.layer})
        elif tipo == "trace" and acao.corners:
            msp.add_trace(*acao.corners, dxfattribs={"layer": acao.layer})
        elif tipo == "helix" and acao.centro and hasattr(acao, 'height'):
            msp.add_helix(base=tuple(acao.centro), height=acao.height, turns=acao.turns, dxfattribs={"layer": acao.layer})
        elif tipo == "wipeout" and acao.contorno:
            msp.add_wipeout([tuple(v) for v in acao.contorno], dxfattribs={"layer": acao.layer})
        elif tipo == "attdef" and acao.tag and acao.prompt and acao.insert:
            msp.add_attdef(tag=acao.tag, prompt=acao.prompt, insert=tuple(acao.insert), dxfattribs={"layer": acao.layer})
        # Edição de Geometria
        elif tipo == "offset" and acao.layer and acao.distance is not None:
            for e in list(msp):
                if e.dxf.layer == acao.layer:
                    e.offset(acao.distance)
        elif tipo == "explode":
            for e in list(msp):
                if e.dxftype() in ("INSERT","LWPOLYLINE","HATCH"):
                    try:
                        for o in e.explode():
                            msp.add_entity(o)
                        msp.delete_entity(e)
                    except Exception:
                        continue
        elif tipo == "mirror" and acao.inicio and acao.direcao:
            mat = mirror_matrix(tuple(acao.inicio), tuple(acao.direcao))
            doc.transform(mat)
        elif tipo == "move" and acao.dx is not None and acao.dy is not None:
            m = Matrix44.translate(acao.dx, acao.dy, 0)
            doc.transform(m)
        elif tipo == "rotate" and acao.angle is not None and acao.center:
            m = Matrix44.z_rotate(acao.angle, axis=tuple(acao.center))
            doc.transform(m)
        elif tipo == "scale" and acao.scale_x is not None and acao.scale_y is not None:
            m = Matrix44.scale(acao.scale_x, acao.scale_y, 1.0)
            doc.transform(m)

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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf, requests, os, base64, re, json
from datetime import datetime
import pytz
from typing import Optional, List

app = FastAPI()

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
    nome: Optional[str]
    cor: Optional[int]
    inicio: Optional[List[float]]
    fim: Optional[List[float]]
    layer: Optional[str]
    vertices: Optional[List[List[float]]]
    centro: Optional[List[float]]
    raio: Optional[float]
    angulo_inicio: Optional[float]
    angulo_fim: Optional[float]
    major_axis: Optional[List[float]]
    minor_radius: Optional[float]
    major_radius: Optional[float]
    canto1: Optional[List[float]]
    canto2: Optional[List[float]]
    local: Optional[List[float]]
    direcao: Optional[List[float]]
    pontos: Optional[List[List[float]]]
    inner_radius: Optional[float]
    outer_radius: Optional[float]
    corners: Optional[List[List[float]]]
    base: Optional[List[float]]
    height: Optional[float]
    turns: Optional[int]
    contorno: Optional[List[List[float]]]
    tag: Optional[str]
    prompt: Optional[str]
    insert: Optional[List[float]]
    distance: Optional[float]
    p1: Optional[List[float]]
    p2: Optional[List[float]]
    dx: Optional[float]
    dy: Optional[float]
    angle: Optional[float]
    center: Optional[List[float]]
    scale_x: Optional[float]
    scale_y: Optional[float]

class ExecutarAcoesRequest(BaseModel):
    file_url: str
    acoes: List[Acao]

# ─── Helpers de aprendizado ─────────────────────────────────────────────────
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

    # Timestamp no fuso de Brasília
    br_tz    = pytz.timezone("America/Sao_Paulo")
    ts       = datetime.now(br_tz).strftime("%Y%m%d_%H%M%S")
    filename = f"saida_{ts}.dxf"

    original_path = os.path.join(temp_dir, "baixado.dxf")
    modified_path = os.path.join(temp_dir, filename)
    github_api    = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    raw_url       = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"

    # 1) Download
    resp = requests.get(data.file_url)
    if resp.status_code != 200:
        return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: {resp.status_code}"})
    with open(original_path, "wb") as f:
        f.write(resp.content)

    # 2) Abrir e modificar
    try:
        doc = ezdxf.readfile(original_path)
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

        doc.saveas(modified_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao processar DXF: {str(e)}"})

    # 3) Upload para GitHub
    with open(modified_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"message": f"upload {filename}", "content": content_b64, "branch": "main"}
    put = requests.put(github_api, json=payload, headers=headers)
    if put.status_code not in (200, 201):
        return JSONResponse(status_code=500, content={"error": "Falha no upload", "detalhes": put.json()})

    return JSONResponse(content={"mensagem": "Arquivo modificado com sucesso", "download_url": raw_url})

# ─── Endpoint 2: comandos aprendidos ─────────────────────────────────────────
@app.post("/executar_comando/")
def executar_comando(data: ExecutarComandoRequest):
    if not data.file_url or not data.comando:
        return JSONResponse(status_code=400, content={"error": "'file_url' e 'comando' são obrigatórios"})

    # Ler knowledge.jsonl
    etapas = []
    if os.path.exists(KNOWLEDGE_PATH):
        for linha in open(KNOWLEDGE_PATH):
            reg = json.loads(linha)
            if reg.get("comando") == data.comando and "etapas" in reg:
                etapas = reg["etapas"]
                break

    if not etapas:
        return JSONResponse(status_code=404, content={"error": f"Comando '{data.comando}' não encontrado"})

    instr = ", ".join(etapas)
    return modificar_dxf_url(DXFUrlRequest(file_url=data.file_url, instrucoes=instr))

# ─── Endpoint 3: ações CAD detalhadas ────────────────────────────────────────
@app.post("/executar_acoes/")
async def executar_acoes_endpoint(request: Request):
    try:
        data = await request.json()
        file_url = data.get("file_url")
        acoes    = data.get("acoes", [])
        if not file_url or not isinstance(acoes, list):
            return JSONResponse(status_code=400, content={"error": "'file_url' e 'acoes' são obrigatórios"})

        # Preparar paths
        temp_dir = "/tmp/dxf_api"
        os.makedirs(temp_dir, exist_ok=True)
        br_tz    = pytz.timezone("America/Sao_Paulo")
        ts       = datetime.now(br_tz).strftime("%Y%m%d_%H%M%S")
        filename = f"saida_{ts}.dxf"
        orig     = os.path.join(temp_dir, "baixado.dxf")
        dest     = os.path.join(temp_dir, filename)
        github_api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
        raw_url    = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"

        # Download
        resp = requests.get(file_url)
        if resp.status_code != 200:
            return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: {resp.status_code}"})
        with open(orig, "wb") as f:
            f.write(resp.content)

        # Abrir DXF
        doc = ezdxf.readfile(orig)
        msp = doc.modelspace()

        # Executar ações
        from ezdxf.math import mirror_matrix, Matrix44
        from ezdxf.entities import MLine

        for ac in acoes:
            tipo = ac.get("tipo", "").lower()

            # ── criar layer ───────────────────────────
            if tipo == "criar_layer" and ac.get("nome"):
                if ac["nome"] not in doc.layers:
                    doc.layers.new(name=ac["nome"], dxfattribs={"color": ac.get("cor", 7)})
                    msp.add_point((0, 0), dxfattribs={"layer": ac["nome"]})

            # ── Entidades Básicas ──────────────────────
            elif tipo in ("line", "desenhar_linha"):
                msp.add_line(tuple(ac["inicio"]), tuple(ac["fim"]), dxfattribs={"layer": ac["layer"]})
            elif tipo in ("pline", "polylinha"):
                msp.add_lwpolyline([tuple(v) for v in ac["vertices"]], dxfattribs={"layer": ac["layer"]})
            elif tipo in ("circle", "desenhar_circulo"):
                msp.add_circle(tuple(ac["centro"]), ac["raio"], dxfattribs={"layer": ac["layer"]})
            elif tipo in ("arc", "desenhar_arco"):
                msp.add_arc(tuple(ac["centro"]), ac["raio"], ac["angulo_inicio"], ac["angulo_fim"],
                            dxfattribs={"layer": ac["layer"]})
            elif tipo in ("ellipse", "desenhar_elipse"):
                major = tuple(ac["major_axis"])
                ratio = ac["minor_radius"] / ac["major_radius"]
                msp.add_ellipse(center=tuple(ac["centro"]), major_axis=major, ratio=ratio,
                                dxfattribs={"layer": ac["layer"]})
            elif tipo in ("rectangle", "desenhar_retangulo"):
                x1, y1 = ac["canto1"]; x2, y2 = ac["canto2"]
                pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
                msp.add_lwpolyline(pts, dxfattribs={"layer": ac["layer"]})
            elif tipo in ("point", "desenhar_ponto"):
                msp.add_point(tuple(ac["local"]), dxfattribs={"layer": ac["layer"]})
            elif tipo == "ray":
                msp.add_ray(tuple(ac["inicio"]), tuple(ac["direcao"]), dxfattribs={"layer": ac["layer"]})
            elif tipo == "xline":
                msp.add_xline(tuple(ac["inicio"]), tuple(ac["direcao"]), dxfattribs={"layer": ac["layer"]})
            elif tipo in ("mline", "multiline"):
                msp.add_mline([tuple(v) for v in ac["vertices"]], override={"color": ac.get("cor", 7)})

            # ── Entidades Avançadas ────────────────────
            elif tipo == "spline":
                msp.add_spline(control_points=[tuple(p) for p in ac["pontos"]], dxfattribs={"layer": ac["layer"]})
            elif tipo == "hatch":
                hatch = msp.add_hatch(color=ac.get("cor", 7))
                hatch.paths.add_polyline_path([tuple(v) for v in ac["vertices"]], is_closed=True)
            elif tipo == "region":
                reg = doc.entities.new("REGION"); reg.append_polygon([tuple(v) for v in ac["vertices"]])
            elif tipo == "donut":
                msp.add_donut(ac["inner_radius"], ac["outer_radius"], dxfattribs={"layer": ac["layer"]})
            elif tipo == "solid":
                msp.add_solid([tuple(v) for v in ac["vertices"]], dxfattribs={"layer": ac["layer"]})
            elif tipo == "trace":
                msp.add_trace(*ac["corners"], dxfattribs={"layer": ac["layer"]})
            elif tipo == "helix":
                msp.add_helix(base=tuple(ac["base"]), height=ac["height"], turns=ac["turns"],
                              dxfattribs={"layer": ac["layer"]})
            elif tipo == "wipeout":
                msp.add_wipeout([tuple(v) for v in ac["contorno"]], dxfattribs={"layer": ac["layer"]})
            elif tipo == "attdef":
                msp.add_attdef(tag=ac["tag"], prompt=ac["prompt"], insert=tuple(ac["insert"]),
                               dxfattribs={"layer": ac["layer"]})

            # ── Edição de Geometria ───────────────────
            elif tipo == "offset":
                for e in list(msp):
                    if e.dxf.layer == ac["layer"]:
                        e.offset(ac["distance"])
            elif tipo == "explode":
                for e in list(msp):
                    if e.dxftype() in ("INSERT", "LWPOLYLINE", "HATCH"):
                        try:
                            for o in e.explode(): msp.add_entity(o)
                            msp.delete_entity(e)
                        except Exception:
                            pass
            elif tipo == "mirror":
                mat = mirror_matrix(tuple(ac["p1"]), tuple(ac["p2"])); doc.transform(mat)
            elif tipo == "move":
                m = Matrix44.translate(ac["dx"], ac["dy"], 0); doc.transform(m)
            elif tipo == "rotate":
                m = Matrix44.z_rotate(ac["angle"], axis=tuple(ac["center"])); doc.transform(m)
            elif tipo == "scale":
                m = Matrix44.scale(ac["scale_x"], ac["scale_y"], 1.0); doc.transform(m)

        # Salvar alterações
        doc.saveas(dest)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Internal Server Error", "detalhes": str(e)})

    # Upload para GitHub
    with open(dest, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    put = requests.put(
        github_api,
        json={"message": f"upload {filename}", "content": content_b64, "branch": "main"},
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    )
    if put.status_code not in (200, 201):
        return JSONResponse(status_code=500, content={"error": "Falha no upload", "detalhes": put.json()})

    return JSONResponse(content={"mensagem": "Arquivo modificado com sucesso", "download_url": raw_url})

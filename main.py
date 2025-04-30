from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf, requests, os, base64, re
from datetime import datetime
import pytz
from typing import Optional

app = FastAPI()

GITHUB_REPO = "lucasjordann/api-ezdxf"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

class DXFUrlRequest(BaseModel):
    file_url: str
    instrucoes: Optional[str] = None

@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)

    # 🕓 Timestamp com fuso horário do Brasil
    br_tz = pytz.timezone("America/Sao_Paulo")
    timestamp = datetime.now(br_tz).strftime("%Y%m%d_%H%M%S")
    filename = f"saida_{timestamp}.dxf"

    original_path = os.path.join(temp_dir, "baixado.dxf")
    modified_path = os.path.join(temp_dir, filename)
    github_api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{filename}"

    # 🔽 Etapa 1 – Baixar DXF original
    try:
        response = requests.get(data.file_url)
        if response.status_code != 200:
            return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: status {response.status_code}"})
        with open(original_path, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Falha ao baixar arquivo: {str(e)}"})

    # 🔽 Etapa 2 – Modificar com ezdxf
    try:
        doc = ezdxf.readfile(original_path)
        msp = doc.modelspace()

        # Texto padrão para validação visual
        msp.add_text("Texto via API", dxfattribs={"insert": (100, 100)})

        if data.instrucoes:
            texto = data.instrucoes.lower()

            # 🎨 Mudar cor das polilinhas
            match_cor = re.search(r"cor das polilinhas para (\d+)", texto)
            if match_cor:
                cor = int(match_cor.group(1))
                for e in msp:
                    if e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                        e.dxf.color = cor

            # 🔵 Adicionar círculos
            match_circulos = re.search(r"adicionar (\d+) círculos?", texto)
            if match_circulos:
                n = int(match_circulos.group(1))
                for i in range(n):
                    msp.add_circle(center=(50 + i*20, 50), radius=5)

        doc.saveas(modified_path)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao processar/modificar DXF: {str(e)}"})

    # 🔽 Etapa 3 – Upload para GitHub
    try:
        with open(modified_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        payload = {
            "message": f"upload {filename}",
            "content": content_b64,
            "branch": "main"
        }

        put_resp = requests.put(github_api_url, json=payload, headers=headers)
        if put_resp.status_code not in [200, 201]:
            return JSONResponse(status_code=500, content={
                "error": "Erro ao fazer upload para GitHub",
                "detalhes": put_resp.json()
            })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro durante upload para GitHub: {str(e)}"})

    # 🔚 Link 100% confiável (raw)
    return JSONResponse(content={
        "mensagem": "Arquivo modificado com sucesso",
        "download_url": raw_url
    })

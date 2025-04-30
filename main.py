from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf, requests, os, base64

app = FastAPI()

# Dados fixos do repositório e token (provisório, melhor usar variável no Render depois)
GITHUB_REPO = "lucasjordann/api-ezdxf"
GITHUB_TOKEN = "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"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/saida.dxf"

class DXFUrlRequest(BaseModel):
    file_url: str

@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)
    original_path = os.path.join(temp_dir, "baixado.dxf")
    modified_path = os.path.join(temp_dir, "saida.dxf")

    # Etapa 1 – Download
    try:
        response = requests.get(data.file_url)
        if response.status_code != 200:
            return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: status {response.status_code}"})
        with open(original_path, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Falha ao baixar arquivo: {str(e)}"})

    # Etapa 2 – Modificar DXF
    try:
        doc = ezdxf.readfile(original_path)
        msp = doc.modelspace()
        msp.add_text("Texto via API", dxfattribs={"insert": (100, 100)})
        doc.saveas(modified_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao modificar/salvar DXF: {str(e)}"})

    # Etapa 3 – Upload para GitHub
    try:
        with open(modified_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        # Verificar se o arquivo já existe (para obter SHA)
        get_resp = requests.get(GITHUB_API_URL, headers=headers)
        sha = get_resp.json().get("sha", None)

        payload = {
            "message": "upload automático do DXF modificado",
            "content": content_b64,
            "branch": "main"
        }
        if sha:
            payload["sha"] = sha  # Necessário se o arquivo já existir

        put_resp = requests.put(GITHUB_API_URL, json=payload, headers=headers)

        if put_resp.status_code not in [200, 201]:
            return JSONResponse(status_code=500, content={
                "error": f"Erro ao fazer upload para GitHub",
                "detalhes": put_resp.json()
            })

        raw_url = "https://raw.githubusercontent.com/lucasjordann/api-ezdxf/main/saida.dxf"
        return JSONResponse(content={
            "mensagem": "Arquivo modificado com sucesso",
            "download_url": raw_url
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro durante upload para GitHub: {str(e)}"})

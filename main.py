from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import ezdxf, requests, os, base64, time

app = FastAPI()

# Variáveis do GitHub
GITHUB_REPO = "lucasjordann/api-ezdxf"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/saida.dxf"
RAW_URL = "https://raw.githubusercontent.com/lucasjordann/api-ezdxf/main/saida.dxf"

class DXFUrlRequest(BaseModel):
    file_url: str

@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)
    original_path = os.path.join(temp_dir, "baixado.dxf")
    modified_path = os.path.join(temp_dir, "saida.dxf")

    # Etapa 1 – Download do arquivo original
    try:
        response = requests.get(data.file_url)
        if response.status_code != 200:
            return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: status {response.status_code}"})
        with open(original_path, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Falha ao baixar arquivo: {str(e)}"})

    # Etapa 2 – Modificar com ezdxf
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

        get_resp = requests.get(GITHUB_API_URL, headers=headers)
        sha = get_resp.json().get("sha", None)

        payload = {
            "message": "upload automático do DXF modificado",
            "content": content_b64,
            "branch": "main"
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(GITHUB_API_URL, json=payload, headers=headers)
        if put_resp.status_code not in [200, 201]:
            return JSONResponse(status_code=500, content={
                "error": "Erro ao fazer upload para GitHub",
                "detalhes": put_resp.json()
            })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro durante upload para GitHub: {str(e)}"})

    # Etapa 4 – Baixar novamente da URL raw do GitHub
    try:
        final_path = os.path.join(temp_dir, "final_saida.dxf")
        raw_response = requests.get(RAW_URL)
        with open(final_path, "wb") as f:
            f.write(raw_response.content)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao baixar do GitHub para devolução: {str(e)}"})

    # Etapa 5 – Devolver o arquivo diretamente como download
    return FileResponse(final_path, media_type="application/dxf", filename="saida.dxf")

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf, requests, os

app = FastAPI()

class DXFUrlRequest(BaseModel):
    file_url: str

@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)
    original_path = os.path.join(temp_dir, "baixado.dxf")

    # 🔽 Etapa 1: baixar o arquivo
    try:
        response = requests.get(data.file_url)
        if response.status_code != 200:
            return JSONResponse(status_code=400, content={"error": f"Erro ao baixar: status {response.status_code}"})
        with open(original_path, "wb") as f:
            f.write(response.content)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Falha ao baixar arquivo: {str(e)}"})

    # 🔽 Etapa 2: validar arquivo
    if not os.path.exists(original_path) or os.path.getsize(original_path) == 0:
        return JSONResponse(status_code=400, content={"error": "Arquivo baixado está vazio ou não existe"})

    # 🔽 Etapa 3: abrir com ezdxf
    try:
        doc = ezdxf.readfile(original_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao abrir DXF: {str(e)}"})

    # 🔽 Etapa 4: modificar o DXF
    try:
        msp = doc.modelspace()
        msp.add_text("Texto via API", dxfattribs={"insert": (100, 100)})
        modified_path = os.path.join(temp_dir, "modificado.dxf")
        doc.saveas(modified_path)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro ao modificar/salvar DXF: {str(e)}"})

    # 🔽 Etapa 5: upload para file.io
    try:
        with open(modified_path, "rb") as file:
            upload = requests.post("https://file.io", files={"file": file})
        if upload.status_code != 200:
            return JSONResponse(status_code=500, content={"error": f"Erro ao fazer upload: status {upload.status_code}"})
        upload_data = upload.json()
        if not upload_data.get("success"):
            return JSONResponse(status_code=500, content={"error": "Upload falhou", "detalhes": upload_data})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Erro durante upload: {str(e)}"})

    # 🔽 Sucesso!
    return JSONResponse(content={
        "mensagem": "Arquivo modificado com sucesso",
        "download_url": upload_data["link"]
    })

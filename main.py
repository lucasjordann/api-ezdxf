from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import ezdxf, shutil, os, requests

app = FastAPI()

# Função que salva e modifica o DXF vindo de uma URL
class DXFUrlRequest(BaseModel):
    file_url: str

@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)
    original_path = os.path.join(temp_dir, "baixado.dxf")

    # Baixar o arquivo
    response = requests.get(data.file_url)
    if response.status_code != 200:
        return {"error": f"Erro ao baixar o arquivo: status {response.status_code}"}

    with open(original_path, "wb") as f:
        f.write(response.content)

    if not os.path.exists(original_path) or os.path.getsize(original_path) == 0:
        return {"error": "Arquivo DXF baixado está vazio ou inválido"}

    try:
        doc = ezdxf.readfile(original_path)
    except Exception as e:
        return {"error": f"Falha ao abrir o arquivo DXF: {str(e)}"}

    # Modificação simples no DXF
    msp = doc.modelspace()
    msp.add_text("Texto via API", dxfattribs={"insert": (100, 100)})

    modified_path = os.path.join(temp_dir, "modificado.dxf")
    doc.saveas(modified_path)

    # Enviar o arquivo modificado para file.io
    with open(modified_path, "rb") as file_to_upload:
        upload_response = requests.post("https://file.io", files={"file": file_to_upload})

    if upload_response.status_code != 200:
        return {"error": "Erro ao fazer upload do arquivo modificado"}

    upload_data = upload_response.json()
    if not upload_data.get("success"):
        return {"error": "Upload falhou", "detalhes": upload_data}

    # Retornar o link público
    return JSONResponse(content={
        "mensagem": "Arquivo modificado com sucesso",
        "download_url": upload_data["link"]
    })

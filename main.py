from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
import ezdxf, shutil, os, requests

app = FastAPI()

@app.post("/modificar_dxf/")
async def modificar_dxf(file: UploadFile = File(...)):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)
    original_path = os.path.join(temp_dir, file.filename)
    with open(original_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    doc = ezdxf.readfile(original_path)
    msp = doc.modelspace()
    msp.add_text("Texto gerado via API", dxfattribs={"insert": (100, 100)})
    modified_path = os.path.join(temp_dir, f"modificado_{file.filename}")
    doc.saveas(modified_path)
    return FileResponse(modified_path, media_type="application/dxf", filename=f"modificado_{file.filename}")

class DXFUrlRequest(BaseModel):
    file_url: str

@app.post("/modificar_dxf_url/")
def modificar_dxf_url(data: DXFUrlRequest):
    temp_dir = "/tmp/dxf_api"
    os.makedirs(temp_dir, exist_ok=True)
    original_path = os.path.join(temp_dir, "baixado.dxf")

    # Baixa o arquivo a partir da URL
    response = requests.get(data.file_url)
    if response.status_code != 200:
        return {"error": f"Erro ao baixar o arquivo: status {response.status_code}"}
    
    with open(original_path, "wb") as f:
        f.write(response.content)

    if not os.path.exists(original_path) or os.path.g_

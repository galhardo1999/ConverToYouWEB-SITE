from flask import Flask, request, send_file, render_template
from flask_socketio import SocketIO, emit
import os
import rawpy
from PIL import Image, ImageOps
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua-chave-secreta-aqui'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limite de upload
socketio = SocketIO(app)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def processar_arquivo(arquivo, baixa_resolucao=False):
    """Converte um arquivo RAW (.cr2, .cr3, .nef) para JPEG."""
    try:
        caminho_arquivo = os.path.join(UPLOAD_FOLDER, arquivo.filename)
        os.makedirs(os.path.dirname(caminho_arquivo), exist_ok=True)
        arquivo.save(caminho_arquivo)
        print(f"Salvou: {caminho_arquivo}")
        
        with rawpy.imread(caminho_arquivo) as raw:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                imagem = Image.open(io.BytesIO(thumb.data))
                imagem = ImageOps.exif_transpose(imagem)
            else:
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    use_auto_wb=False,
                    no_auto_bright=False,
                    output_color=rawpy.ColorSpace.sRGB,
                    highlight_mode=rawpy.HighlightMode.Clip
                )
                imagem = Image.fromarray(rgb)

        if baixa_resolucao:
            largura, altura = imagem.size
            if largura > altura:
                nova_largura = 1920
                nova_altura = int((1920 / largura) * altura)
            else:
                nova_altura = 1920
                nova_largura = int((1920 / altura) * largura)
            imagem = imagem.resize((nova_largura, nova_altura), Image.Resampling.BICUBIC)

        output = io.BytesIO()
        imagem.save(output, 'JPEG', quality=85)
        output.seek(0)
        os.remove(caminho_arquivo)
        print(f"Convertido para JPEG: {arquivo.filename}")
        return output, arquivo.filename.replace('.NEF', '.jpg').replace('.CR2', '.jpg').replace('.CR3', '.jpg')
    except Exception as e:
        os.remove(caminho_arquivo) if os.path.exists(caminho_arquivo) else None
        return f"Erro ao converter {os.path.basename(arquivo.filename)}: {str(e)}", arquivo.filename

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    print("Requisição POST recebida em /upload")
    arquivos = request.files.getlist('files')
    baixa_resolucao = request.form.get('baixa_resolucao') == 'on'
    
    if not arquivos or len(arquivos) == 0 or all(not arq.filename for arq in arquivos):
        print("Nenhum arquivo recebido")
        socketio.emit('progresso', {'mensagem': 'Nenhuma pasta ou arquivos enviados', 'progresso': 0, 'erro': True})
        return "Nenhum arquivo enviado", 400
    
    print(f"Recebeu {len(arquivos)} arquivos: {[arq.filename for arq in arquivos]}")
    total_arquivos = len(arquivos)
    arquivos_convertidos = 0
    resultados = {}
    formatos_validos = ('.cr2', '.cr3', '.nef')

    arquivos_validos = [arq for arq in arquivos if arq.filename.lower().endswith(formatos_validos)]
    if not arquivos_validos:
        print("Nenhum arquivo válido encontrado")
        socketio.emit('progresso', {'mensagem': 'Nenhum arquivo .cr2, .cr3 ou .nef encontrado', 'progresso': 0, 'erro': True})
        return "Nenhum arquivo válido", 400

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {executor.submit(processar_arquivo, arquivo, baixa_resolucao): arquivo for arquivo in arquivos_validos}
        
        for future in as_completed(futures):
            resultado, nome_arquivo = future.result()
            arquivos_convertidos += 1
            progresso = (arquivos_convertidos / total_arquivos) * 100
            
            if isinstance(resultado, str):
                print(f"Erro: {resultado}")
                socketio.emit('progresso', {'mensagem': resultado, 'progresso': progresso, 'erro': True})
            else:
                resultados[nome_arquivo] = resultado
                socketio.emit('progresso', {'mensagem': f'Convertendo: {os.path.basename(nome_arquivo)}', 'progresso': progresso, 'erro': False})

    if resultados:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for nome_arquivo, conteudo in resultados.items():
                zip_file.writestr(nome_arquivo, conteudo.read())
        zip_buffer.seek(0)
        
        zip_path = os.path.join(UPLOAD_FOLDER, 'imagens_convertidas.zip')
        with open(zip_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
        
        print("Conversão concluída, ZIP gerado")
        socketio.emit('concluido', {'mensagem': 'Conversão concluída!', 'progresso': 100})
        socketio.emit('download', {'url': '/download_zip'})
    
    return "Processamento iniciado", 200

@app.route('/download_zip')
def download_zip():
    zip_path = os.path.join(UPLOAD_FOLDER, 'imagens_convertidas.zip')
    if os.path.exists(zip_path):
        return send_file(zip_path, mimetype='application/zip', as_attachment=True, download_name='imagens_convertidas.zip')
    return "Arquivo não encontrado", 404

if __name__ == '__main__':
    socketio.run(app, debug=True)
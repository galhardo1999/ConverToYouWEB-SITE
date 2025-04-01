const socket = io();
const form = document.getElementById('upload-form');
const status = document.getElementById('status');
const progressFill = document.getElementById('progress-fill');

form.addEventListener('submit', (e) => {
    console.log('Formulário enviado');
    status.textContent = 'Iniciando conversão...';
    progressFill.style.width = '0%';
});

socket.on('progresso', (data) => {
    console.log('Progresso:', data);
    status.textContent = data.mensagem;
    progressFill.style.width = `${data.progresso}%`;
    if (data.erro) {
        progressFill.style.backgroundColor = '#D32F2F';
    }
});

socket.on('concluido', (data) => {
    console.log('Concluído:', data);
    status.textContent = data.mensagem;
    progressFill.style.width = `${data.progresso}%`;
});

socket.on('download', (data) => {
    console.log('Download:', data);
    const a = document.createElement('a');
    a.href = data.url;
    a.download = 'imagens_convertidas.zip';
    a.click();
});
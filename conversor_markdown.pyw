#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversor Markdown - interface grafica para converter documentos em .md

PDF pelo pypdfium2 (rapido). Demais formatos pelo MarkItDown (Microsoft).
Opcao de remover o rodape repetido do PJe, que ocupa cerca de 20% do arquivo.

Requisitos:
    pip install pypdfium2 "markitdown[all]"

Uso:
    Duplo clique no arquivo.

Licenca MIT. Veja o arquivo LICENSE.
"""

import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Conversor Markdown"

EXTENSOES = [
    ("Todos os suportados",
     "*.pdf *.docx *.doc *.pptx *.xlsx *.xls *.csv *.html *.htm *.txt "
     "*.rtf *.epub *.json *.xml *.zip *.png *.jpg *.jpeg"),
    ("PDF", "*.pdf"),
    ("Word", "*.docx *.doc"),
    ("PowerPoint", "*.pptx"),
    ("Excel", "*.xlsx *.xls *.csv"),
    ("Imagens", "*.png *.jpg *.jpeg"),
    ("Todos os arquivos", "*.*"),
]

PENDENTE = "•"
RODANDO = "▶"
OK = "✓"
ERRO = "✕"

# Linhas de rodape/carimbo que o PJe repete em toda pagina.
PADROES_RODAPE = [
    r"^Este documento foi gerado pelo usuário .*$",
    r"^Número do processo: \d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\s*$",
    r"^Número do documento: \d+ \| Tipo de documento: .*$",
    r"^https?://pje\S*$",
    r"^Assinado eletronicamente por: .*$",
    r"^Perfil: .*Num\. \d+ - Pág\. \d+\s*$",
    r"^Perfil: \S+\s*$",
    r"^Num\. \d+ - Pág\. \d+\s*$",
]
RX_RODAPE = re.compile("|".join(PADROES_RODAPE), re.MULTILINE)


def limpar_rodape(texto):
    texto = RX_RODAPE.sub("", texto)
    return re.sub(r"\n{3,}", "\n\n", texto)


# Ligaduras tipograficas que o PDF preserva e quebram a busca com Ctrl+F.
LIGADURAS = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "ft", "ﬆ": "st", "­": "",
}


def normalizar_ligaduras(texto):
    for origem, destino in LIGADURAS.items():
        texto = texto.replace(origem, destino)
    return texto


def normalizar_espacos(texto):
    """Colapsa espacos multiplos de texto justificado, fora de tabelas."""
    texto = normalizar_ligaduras(texto)
    saida = []
    for linha in texto.split("\n"):
        if linha.lstrip().startswith("|"):
            saida.append(linha)
        else:
            saida.append(re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", linha))
    return "\n".join(saida)


# ------------------------------------------------------------------ motores

def converter_pdf_rapido(caminho):
    """Extracao rapida via pypdfium2 (motor PDFium, licenca BSD/Apache)."""
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(caminho)
    partes = []
    try:
        for indice in range(len(documento)):
            pagina = documento[indice]
            pagina_texto = pagina.get_textpage()
            try:
                partes.append(pagina_texto.get_text_range())
            finally:
                pagina_texto.close()
                pagina.close()
    finally:
        documento.close()
    return "\n".join(partes).replace("\r\n", "\n").replace("\r", "\n")


def converter_pdf_tabelas(caminho, markitdown):
    return (markitdown.convert(caminho).text_content or "")


def converter_generico(caminho, markitdown):
    return (markitdown.convert(caminho).text_content or "")


class ConversorApp:
    def __init__(self, root):
        self.root = root
        self.arquivos = []
        self.status = {}
        self.destino_custom = None
        self.fila = queue.Queue()
        self.convertendo = False
        self.ultima_pasta_saida = None
        self.markitdown = None

        root.title(APP_TITLE)
        root.geometry("680x540")
        root.minsize(600, 480)

        self._montar_interface()
        self._verificar_dependencias()
        self.root.after(100, self._processar_fila)

    # ---------------------------------------------------------------- UI

    def _montar_interface(self):
        topo = ttk.Frame(self.root)
        topo.pack(fill="x", padx=12, pady=(12, 6))

        self.btn_escolher = ttk.Button(
            topo, text="Escolher arquivos...", command=self.escolher_arquivos
        )
        self.btn_escolher.pack(side="left")

        self.btn_limpar = ttk.Button(topo, text="Limpar lista", command=self.limpar_lista)
        self.btn_limpar.pack(side="left", padx=(8, 0))

        self.lbl_contagem = ttk.Label(topo, text="Nenhum arquivo selecionado")
        self.lbl_contagem.pack(side="right")

        moldura = ttk.Frame(self.root)
        moldura.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        self.lista = tk.Listbox(
            moldura, activestyle="none", highlightthickness=0,
            selectmode="extended", font=("Consolas", 10),
        )
        barra = ttk.Scrollbar(moldura, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.lista.bind("<Delete>", self._remover_selecionados)

        self.progresso = ttk.Progressbar(self.root, mode="determinate")
        self.progresso.pack(fill="x", padx=12)

        self.lbl_status = ttk.Label(self.root, text="Pronto.", anchor="w")
        self.lbl_status.pack(fill="x", padx=12, pady=(4, 6))

        # Opcoes
        opcoes = ttk.LabelFrame(self.root, text="Opções")
        opcoes.pack(fill="x", padx=12, pady=(0, 6))

        self.var_limpar_rodape = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opcoes,
            text="Remover rodapé repetido do PJe  (reduz o arquivo em cerca de 20%)",
            variable=self.var_limpar_rodape,
        ).pack(anchor="w", padx=8, pady=(6, 0))

        self.var_tabelas = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opcoes,
            text="Detectar tabelas nos PDFs  (bem mais lento, use só se precisar)",
            variable=self.var_tabelas,
        ).pack(anchor="w", padx=8, pady=(0, 6))

        # Destino
        destino = ttk.Frame(self.root)
        destino.pack(fill="x", padx=12)

        ttk.Label(destino, text="Destino:").pack(side="left")
        self.var_destino = tk.StringVar(value="mesma")
        ttk.Radiobutton(
            destino, text="Mesma pasta do original", value="mesma",
            variable=self.var_destino, command=self._atualizar_destino,
        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(
            destino, text="Escolher pasta...", value="custom",
            variable=self.var_destino, command=self._atualizar_destino,
        ).pack(side="left", padx=(8, 0))

        self.lbl_destino = ttk.Label(self.root, text="", foreground="#555", anchor="w")
        self.lbl_destino.pack(fill="x", padx=12)

        rodape = ttk.Frame(self.root)
        rodape.pack(fill="x", padx=12, pady=12)

        self.btn_converter = ttk.Button(
            rodape, text="Converter", command=self.iniciar_conversao, state="disabled"
        )
        self.btn_converter.pack(side="right")

        self.btn_abrir = ttk.Button(
            rodape, text="Abrir pasta", command=self.abrir_pasta, state="disabled"
        )
        self.btn_abrir.pack(side="right", padx=(0, 8))

    def _verificar_dependencias(self):
        faltando = []
        try:
            import pypdfium2  # noqa: F401
        except ImportError:
            faltando.append("pypdfium2")
        try:
            from markitdown import MarkItDown
            self.markitdown = MarkItDown()
        except ImportError:
            faltando.append('"markitdown[all]"')

        if faltando:
            self.btn_escolher.config(state="disabled")
            pacotes = " ".join(faltando)
            self.lbl_status.config(text=f"Falta instalar: {pacotes}")
            messagebox.showerror(
                APP_TITLE,
                "Biblioteca ausente.\n\nAbra o Prompt de Comando e execute:\n\n"
                f"    pip install {pacotes}\n\nDepois abra este programa de novo.",
            )

    # ------------------------------------------------------------- acoes

    def escolher_arquivos(self):
        caminhos = filedialog.askopenfilenames(
            title="Selecione os arquivos para converter", filetypes=EXTENSOES
        )
        if not caminhos:
            return
        novos = 0
        for c in caminhos:
            if c not in self.arquivos:
                self.arquivos.append(c)
                self.status[c] = PENDENTE
                novos += 1
        self._redesenhar_lista()
        if novos:
            self.lbl_status.config(text=f"{novos} arquivo(s) adicionado(s).")

    def limpar_lista(self):
        if self.convertendo:
            return
        self.arquivos.clear()
        self.status.clear()
        self.progresso["value"] = 0
        self._redesenhar_lista()
        self.lbl_status.config(text="Lista limpa.")

    def _remover_selecionados(self, _event=None):
        if self.convertendo:
            return
        for indice in sorted(self.lista.curselection(), reverse=True):
            self.status.pop(self.arquivos.pop(indice), None)
        self._redesenhar_lista()

    def _atualizar_destino(self):
        if self.var_destino.get() == "custom":
            pasta = filedialog.askdirectory(title="Pasta de destino dos arquivos .md")
            if pasta:
                self.destino_custom = pasta
                self.lbl_destino.config(text=pasta)
            else:
                self.var_destino.set("mesma")
                self.lbl_destino.config(text="")
        else:
            self.destino_custom = None
            self.lbl_destino.config(text="")

    def abrir_pasta(self):
        pasta = self.ultima_pasta_saida
        if not pasta or not os.path.isdir(pasta):
            return
        if sys.platform.startswith("win"):
            os.startfile(pasta)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", pasta])
        else:
            subprocess.Popen(["xdg-open", pasta])

    # --------------------------------------------------------- conversao

    def iniciar_conversao(self):
        if self.convertendo or not self.arquivos:
            return
        self.convertendo = True
        for widget in (self.btn_converter, self.btn_escolher, self.btn_limpar):
            widget.config(state="disabled")
        self.progresso["value"] = 0
        self.progresso["maximum"] = len(self.arquivos)

        for c in self.arquivos:
            self.status[c] = PENDENTE
        self._redesenhar_lista()

        opcoes = {
            "limpar_rodape": self.var_limpar_rodape.get(),
            "tabelas": self.var_tabelas.get(),
            "destino": self.destino_custom,
        }
        threading.Thread(target=self._trabalhar, args=(opcoes,), daemon=True).start()

    def _trabalhar(self, opcoes):
        total = len(self.arquivos)
        sucesso = 0
        falhas = []
        inicio_geral = time.time()

        for indice, caminho in enumerate(list(self.arquivos)):
            self.fila.put(("status", caminho, RODANDO, None))
            self.fila.put((
                "texto",
                f"Convertendo {indice + 1} de {total}: {os.path.basename(caminho)}",
            ))
            marca = time.time()
            try:
                extensao = os.path.splitext(caminho)[1].lower()
                if extensao == ".pdf" and not opcoes["tabelas"]:
                    texto = converter_pdf_rapido(caminho)
                elif extensao == ".pdf":
                    texto = converter_pdf_tabelas(caminho, self.markitdown)
                else:
                    texto = converter_generico(caminho, self.markitdown)

                texto = normalizar_espacos(texto)
                if opcoes["limpar_rodape"]:
                    texto = limpar_rodape(texto)

                pasta = opcoes["destino"] or os.path.dirname(caminho)
                base = os.path.splitext(os.path.basename(caminho))[0]
                saida = os.path.join(pasta, base + ".md")
                contador = 2
                while os.path.exists(saida):
                    saida = os.path.join(pasta, f"{base} ({contador}).md")
                    contador += 1

                with open(saida, "w", encoding="utf-8") as arquivo:
                    arquivo.write(texto)

                segundos = time.time() - marca
                self.fila.put(("status", caminho, OK, f"{segundos:.1f}s"))
                self.fila.put(("pasta", pasta))
                sucesso += 1
            except Exception as erro:  # noqa: BLE001
                self.fila.put(("status", caminho, ERRO, str(erro)[:70]))
                falhas.append((os.path.basename(caminho), str(erro)))

            self.fila.put(("progresso", indice + 1))

        self.fila.put(("fim", sucesso, total, falhas, time.time() - inicio_geral))

    def _processar_fila(self):
        try:
            while True:
                item = self.fila.get_nowait()
                tipo = item[0]
                if tipo == "status":
                    _, caminho, marca, detalhe = item
                    self.status[caminho] = marca
                    if detalhe:
                        self.detalhes[caminho] = detalhe
                    self._redesenhar_lista()
                elif tipo == "texto":
                    self.lbl_status.config(text=item[1])
                elif tipo == "progresso":
                    self.progresso["value"] = item[1]
                elif tipo == "pasta":
                    self.ultima_pasta_saida = item[1]
                    self.btn_abrir.config(state="normal")
                elif tipo == "fim":
                    self._finalizar(item[1], item[2], item[3], item[4])
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def _finalizar(self, sucesso, total, falhas, segundos):
        self.convertendo = False
        self.btn_converter.config(state="normal" if self.arquivos else "disabled")
        self.btn_escolher.config(state="normal")
        self.btn_limpar.config(state="normal")
        self.lbl_status.config(
            text=f"Concluído. {sucesso} de {total} convertido(s) em {segundos:.1f}s."
        )
        if falhas:
            linhas = "\n".join(f"- {nome}: {msg}" for nome, msg in falhas[:10])
            messagebox.showwarning(APP_TITLE, f"{len(falhas)} arquivo(s) falharam.\n\n{linhas}")

    # ----------------------------------------------------------- helpers

    detalhes = {}

    def _redesenhar_lista(self):
        indice_topo = self.lista.yview()[0]
        self.lista.delete(0, tk.END)
        for caminho in self.arquivos:
            marca = self.status.get(caminho, PENDENTE)
            linha = f" {marca}  {os.path.basename(caminho)}"
            detalhe = self.detalhes.get(caminho)
            if detalhe and marca in (OK, ERRO):
                linha += f"   [{detalhe}]"
            self.lista.insert(tk.END, linha)
        self.lista.yview_moveto(indice_topo)

        quantidade = len(self.arquivos)
        self.lbl_contagem.config(
            text="Nenhum arquivo selecionado" if quantidade == 0 else f"{quantidade} arquivo(s)"
        )
        if not self.convertendo:
            self.btn_converter.config(state="normal" if quantidade else "disabled")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    ConversorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import time
import os
import io
import datetime
from pathlib import Path

import pdf2image
import pytesseract
from pypdf import PdfWriter, PdfReader

ctk.set_appearance_mode("dark")
MAIN_COLOR = "#B06A7C"
HOVER_COLOR = "#8F5362"
BG_SECONDARY = "#2B2B2B"


class AppJuridico(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("⚖ Sistema OCR Jurídico Premium")
        self.geometry("780x900")
        self.resizable(False, False)

        self.arquivos_selecionados = []
        self.is_processing = False
        self.is_paused = False
        self.is_cancelled = False

        self.log_file = Path("LOG_OCR.txt")
        self.error_log_file = Path("LOG_ERROS_OCR.txt")

        self.setup_ui()

    def setup_ui(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(25, 10), fill="x", padx=30)

        ctk.CTkLabel(
            self.header_frame,
            text="OCR Jurídico",
            font=("Georgia", 36, "bold"),
            text_color=MAIN_COLOR,
        ).pack()

        self.main_frame = ctk.CTkFrame(self, corner_radius=20, fg_color=BG_SECONDARY)
        self.main_frame.pack(pady=10, padx=30, fill="both", expand=True)

        self.btn_selecionar = ctk.CTkButton(
            self.main_frame,
            text="📂 CARREGAR PROCESSOS NA FILA",
            font=("Helvetica", 14, "bold"),
            fg_color=MAIN_COLOR,
            hover_color=HOVER_COLOR,
            command=self.selecionar_arquivos,
            height=50,
            corner_radius=10,
        )
        self.btn_selecionar.pack(pady=(25, 10), padx=30, fill="x")

        self.lbl_arquivos = ctk.CTkLabel(
            self.main_frame,
            text="Fila vazia. Selecione PDFs para iniciar.",
            font=("Helvetica", 12),
            text_color="gray70",
        )
        self.lbl_arquivos.pack(pady=(0, 20))

        self.config_frame = ctk.CTkFrame(self.main_frame, fg_color="gray18", corner_radius=15)
        self.config_frame.pack(pady=5, padx=30, fill="x")

        self.smart_skip_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            self.config_frame,
            text="Pular páginas que já têm texto (OCR inteligente)",
            variable=self.smart_skip_var,
            font=("Helvetica", 12),
            progress_color=MAIN_COLOR,
        ).pack(pady=(15, 8), padx=20, anchor="w")

        self.split_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            self.config_frame,
            text="Dividir PDF em partes",
            variable=self.split_var,
            font=("Helvetica", 12),
            progress_color=MAIN_COLOR,
        ).pack(pady=8, padx=20, anchor="w")

        split_cfg = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        split_cfg.pack(padx=20, fill="x", pady=(0, 12))
        ctk.CTkLabel(split_cfg, text="Máximo de folhas por parte:").pack(side="left")
        self.max_paginas_entry = ctk.CTkEntry(split_cfg, width=80)
        self.max_paginas_entry.insert(0, "50")
        self.max_paginas_entry.pack(side="left", padx=8)

        ctk.CTkLabel(
            self.config_frame,
            text="POTÊNCIA DO MOTOR",
            font=("Helvetica", 11, "bold"),
            text_color="gray50",
        ).pack(pady=(5, 0))
        self.motor_var = ctk.StringVar(value="Normal")
        ctk.CTkSegmentedButton(
            self.config_frame,
            values=["Leve (Rápido)", "Normal", "Pesado (Lento)"],
            variable=self.motor_var,
            selected_color=MAIN_COLOR,
            selected_hover_color=HOVER_COLOR,
        ).pack(pady=(5, 15), padx=20, fill="x")

        self.action_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.action_frame.pack(pady=15, padx=30, fill="x")
        self.action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_iniciar = ctk.CTkButton(self.action_frame, text="▶ INICIAR", command=self.iniciar_thread)
        self.btn_iniciar.grid(row=0, column=0, padx=5, sticky="ew")
        self.btn_pausar = ctk.CTkButton(self.action_frame, text="⏸ PAUSAR", state="disabled", command=self.pausar_retomar)
        self.btn_pausar.grid(row=0, column=1, padx=5, sticky="ew")
        self.btn_cancelar = ctk.CTkButton(self.action_frame, text="⏹ CANCELAR", state="disabled", command=self.cancelar)
        self.btn_cancelar.grid(row=0, column=2, padx=5, sticky="ew")

        self.lbl_status = ctk.CTkLabel(self.main_frame, text="Aguardando comando...", font=("Helvetica", 13, "bold"), text_color=MAIN_COLOR)
        self.lbl_status.pack(pady=(15, 0))
        self.lbl_eta = ctk.CTkLabel(self.main_frame, text="", font=("Helvetica", 11), text_color="gray50")
        self.lbl_eta.pack(pady=(0, 5))

        self.progresso = ctk.CTkProgressBar(self.main_frame, progress_color=MAIN_COLOR, height=12)
        self.progresso.pack(pady=5, padx=30, fill="x")
        self.progresso.set(0)

        self.txt_log = ctk.CTkTextbox(self.main_frame, height=150, font=("Consolas", 11), fg_color="#1A1A1A")
        self.txt_log.pack(pady=(10, 25), padx=30, fill="x")

    def write_log_file(self, msg: str, error: bool = False):
        ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        line = f"[{ts}] {msg}\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line)
        if error:
            with open(self.error_log_file, "a", encoding="utf-8") as f:
                f.write(line)

    def log(self, mensagem: str, error: bool = False):
        self.txt_log.insert("end", f"> {mensagem}\n")
        self.txt_log.see("end")
        self.write_log_file(mensagem, error=error)

    def selecionar_arquivos(self):
        arquivos = filedialog.askopenfilenames(title="Selecionar Processos", filetypes=[("PDF", "*.pdf")])
        if arquivos:
            self.arquivos_selecionados = list(arquivos)
            self.lbl_arquivos.configure(text=f"{len(self.arquivos_selecionados)} arquivo(s) na fila.")
            self.log(f"Fila atualizada: {len(self.arquivos_selecionados)} arquivos.")

    def pausar_retomar(self):
        self.is_paused = not self.is_paused
        self.btn_pausar.configure(text="▶ RETOMAR" if self.is_paused else "⏸ PAUSAR")
        self.log("Processo pausado." if self.is_paused else "Processo retomado.")

    def cancelar(self):
        if messagebox.askyesno("Confirmar", "Deseja cancelar o processamento atual?"):
            self.is_cancelled = True
            self.is_paused = False

    def iniciar_thread(self):
        if not self.arquivos_selecionados:
            messagebox.showwarning("Aviso", "Selecione ao menos 1 PDF.")
            return
        self.is_processing = True
        self.is_cancelled = False
        self.btn_iniciar.configure(state="disabled")
        self.btn_pausar.configure(state="normal")
        self.btn_cancelar.configure(state="normal")
        threading.Thread(target=self.processar_fila, daemon=True).start()

    @staticmethod
    def formatar_tempo(segundos):
        m, s = divmod(int(segundos), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def processar_fila(self):
        dpi = {"Leve (Rápido)": 150, "Normal": 200, "Pesado (Lento)": 300}[self.motor_var.get()]
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        max_por_parte = int(self.max_paginas_entry.get() or "50")

        try:
            total_arquivos = len(self.arquivos_selecionados)
            for idx, path in enumerate(self.arquivos_selecionados):
                if self.is_cancelled:
                    break

                nome_base = os.path.splitext(os.path.basename(path))[0]
                self.log(f"Iniciando: {nome_base}")

                reader = PdfReader(path)
                total_paginas = len(reader.pages)
                writer = PdfWriter()
                tempos = []
                volume_count = 1

                for p_num in range(1, total_paginas + 1):
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.3)
                    if self.is_cancelled:
                        break

                    start_t = time.time()
                    self.lbl_status.configure(text=f"Arquivo {idx+1}/{total_arquivos} | Página {p_num}/{total_paginas}")
                    self.progresso.set(((idx / total_arquivos) + (p_num / total_paginas) / total_arquivos))

                    skip = False
                    if self.smart_skip_var.get():
                        try:
                            text = reader.pages[p_num - 1].extract_text()
                            skip = bool(text and len(text.strip()) > 100)
                        except Exception:
                            skip = False

                    if skip:
                        writer.add_page(reader.pages[p_num - 1])
                    else:
                        try:
                            img = pdf2image.convert_from_path(path, first_page=p_num, last_page=p_num, dpi=dpi)[0]
                            pdf_page_bytes = pytesseract.image_to_pdf_or_hocr(img, extension="pdf", lang="por")
                            writer.add_page(PdfReader(io.BytesIO(pdf_page_bytes)).pages[0])
                        except Exception as e:
                            self.log(f"Erro página {p_num} em {nome_base}: {e}", error=True)
                            writer.add_page(reader.pages[p_num - 1])

                    if self.split_var.get() and p_num % max_por_parte == 0:
                        out = os.path.join(desktop, f"{nome_base}_OCR_pt{volume_count:02d}.pdf")
                        with open(out, "wb") as f:
                            writer.write(f)
                        self.log(f"Parte pt{volume_count:02d} salva.")
                        writer = PdfWriter()
                        volume_count += 1

                    tempos.append(time.time() - start_t)
                    avg = sum(tempos[-5:]) / len(tempos[-5:])
                    faltam = avg * (total_paginas - p_num)
                    self.lbl_eta.configure(text=f"Tempo restante estimado: {self.formatar_tempo(faltam)}")

                if not self.is_cancelled and writer.pages:
                    suffix = f"_pt{volume_count:02d}" if self.split_var.get() else ""
                    final_path = os.path.join(desktop, f"{nome_base}_OCR{suffix}.pdf")
                    with open(final_path, "wb") as f:
                        writer.write(f)
                    self.log(f"Concluído: {os.path.basename(final_path)}")

            if not self.is_cancelled:
                self.lbl_status.configure(text="✅ TUDO FINALIZADO!")
                self.progresso.set(1)
                messagebox.showinfo("Sucesso", "Fila concluída com sucesso.")
        except Exception as e:
            self.log(f"ERRO CRÍTICO: {e}", error=True)
            messagebox.showerror("Erro", "Erro crítico no processamento. Veja LOG_ERROS_OCR.txt")
        finally:
            self.reset_ui()

    def reset_ui(self):
        self.is_processing = False
        self.btn_iniciar.configure(state="normal")
        self.btn_pausar.configure(state="disabled", text="⏸ PAUSAR")
        self.btn_cancelar.configure(state="disabled")
        self.lbl_eta.configure(text="")


if __name__ == "__main__":
    app = AppJuridico()
    app.mainloop()

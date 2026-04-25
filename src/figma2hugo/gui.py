from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from figma2hugo.config import OutputMode
from figma2hugo.local_config import get_local_config_path, get_local_figma_token
from figma2hugo.workflow import GenerationOptions, run_generation


class Figma2HugoGUI:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText

        self._tk = tk
        self._ttk = ttk
        self._root = tk.Tk()
        self._root.title("figma2hugo")
        self._root.geometry("760x560")
        self._root.minsize(720, 520)
        self._root.configure(bg="#f3efe7")

        self._queue: Queue[tuple[str, Any]] = Queue()
        self._is_running = False
        self._last_output_dir: Path | None = None

        self.url_var = tk.StringVar()
        self.destination_var = tk.StringVar(value=str(Path.cwd() / "site"))
        self.token_var = tk.StringVar(value=get_local_figma_token() or "")
        self.status_var = tk.StringVar(value="Pret")
        self.summary_var = tk.StringVar(value="Saisis une URL Figma et un dossier de destination.")

        self._build_styles()
        self._build_layout(ScrolledText)
        self._poll_queue()

    def run(self) -> None:
        self._root.mainloop()

    def _build_styles(self) -> None:
        style = self._ttk.Style()
        style.theme_use("clam")
        style.configure("App.TFrame", background="#f3efe7")
        style.configure("Card.TFrame", background="#fffaf2", relief="flat")
        style.configure("Header.TLabel", background="#f3efe7", foreground="#1d2a2f", font=("Segoe UI", 23, "bold"))
        style.configure("Body.TLabel", background="#f3efe7", foreground="#4b5b61", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#fffaf2", foreground="#1d2a2f", font=("Segoe UI", 11, "bold"))
        style.configure("CardBody.TLabel", background="#fffaf2", foreground="#4b5b61", font=("Segoe UI", 10))
        style.configure("Field.TLabel", background="#fffaf2", foreground="#243238", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", background="#d9efe2", foreground="#0d5c3b", font=("Segoe UI", 10, "bold"), padding=(10, 6))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 10))

    def _build_layout(self, scrolled_text_class: type) -> None:
        root = self._root
        ttk = self._ttk

        shell = ttk.Frame(root, style="App.TFrame", padding=24)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        hero = ttk.Frame(shell, style="App.TFrame")
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)

        ttk.Label(hero, text="figma2hugo", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text="Une URL Figma, un dossier cible, puis lancement de la generation.",
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(hero, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")

        form_card = ttk.Frame(shell, style="Card.TFrame", padding=20)
        form_card.grid(row=1, column=0, sticky="ew", pady=(18, 14))
        form_card.columnconfigure(0, weight=1)
        form_card.columnconfigure(1, weight=0)

        ttk.Label(form_card, text="Generation", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            form_card,
            text="Le mode Hugo est le chemin principal. Le statique reste disponible en second bouton.",
            style="CardBody.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))

        ttk.Label(form_card, text="URL Figma", style="Field.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
        self.url_entry = ttk.Entry(form_card, textvariable=self.url_var, font=("Segoe UI", 10))
        self.url_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 14), ipady=6)

        ttk.Label(form_card, text="Dossier de destination", style="Field.TLabel").grid(row=4, column=0, columnspan=2, sticky="w")
        self.destination_entry = ttk.Entry(form_card, textvariable=self.destination_var, font=("Segoe UI", 10))
        self.destination_entry.grid(row=5, column=0, sticky="ew", pady=(6, 0), ipady=6, padx=(0, 10))
        self.browse_button = ttk.Button(form_card, text="Parcourir", style="Secondary.TButton", command=self._choose_directory)
        self.browse_button.grid(row=5, column=1, sticky="ew")

        ttk.Label(form_card, text="Token Figma", style="Field.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.token_entry = ttk.Entry(form_card, textvariable=self.token_var, font=("Consolas", 10), show="*")
        self.token_entry.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0), ipady=6)
        ttk.Label(
            form_card,
            text=f"Optionnel si present dans {get_local_config_path().name}, FIGMA_ACCESS_TOKEN, ou un bridge MCP.",
            style="CardBody.TLabel",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(6, 0))

        actions = ttk.Frame(form_card, style="Card.TFrame")
        actions.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)

        self.generate_hugo_button = ttk.Button(
            actions,
            text="Generer Hugo",
            style="Primary.TButton",
            command=lambda: self._start_generation(OutputMode.HUGO),
        )
        self.generate_hugo_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.generate_static_button = ttk.Button(
            actions,
            text="Exporter Statique",
            style="Secondary.TButton",
            command=lambda: self._start_generation(OutputMode.STATIC),
        )
        self.generate_static_button.grid(row=0, column=1, sticky="ew", padx=4)

        self.open_folder_button = ttk.Button(
            actions,
            text="Ouvrir le dossier",
            style="Secondary.TButton",
            command=self._open_output_dir,
            state="disabled",
        )
        self.open_folder_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        output_card = ttk.Frame(shell, style="Card.TFrame", padding=20)
        output_card.grid(row=2, column=0, sticky="nsew")
        output_card.columnconfigure(0, weight=1)
        output_card.rowconfigure(2, weight=1)

        ttk.Label(output_card, text="Retour", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(output_card, textvariable=self.summary_var, style="CardBody.TLabel").grid(
            row=1, column=0, sticky="w", pady=(4, 12)
        )

        self.output_text = scrolled_text_class(
            output_card,
            wrap="word",
            font=("Consolas", 10),
            padx=12,
            pady=12,
            relief="flat",
            borderwidth=0,
            background="#fffdf8",
            foreground="#203038",
        )
        self.output_text.grid(row=2, column=0, sticky="nsew")
        self.output_text.insert("1.0", "Le rapport de generation apparaitra ici.\n")
        self.output_text.configure(state="disabled")

    def _choose_directory(self) -> None:
        from tkinter import filedialog

        directory = filedialog.askdirectory(initialdir=self.destination_var.get() or str(Path.cwd()))
        if directory:
            self.destination_var.set(directory)

    def _start_generation(self, mode: OutputMode) -> None:
        from tkinter import messagebox

        if self._is_running:
            return

        figma_url = self.url_var.get().strip()
        destination = self.destination_var.get().strip()
        if not figma_url:
            messagebox.showerror("URL manquante", "Saisis une URL Figma.")
            return
        if not destination:
            messagebox.showerror("Destination manquante", "Choisis un dossier de destination.")
            return
        if not _has_figma_access(self.token_var.get()):
            messagebox.showerror(
                "Acces Figma manquant",
                "Aucun acces Figma n'est configure.\n\n"
                "Renseigne un token dans le champ \"Token Figma\"\n"
                f"ou dans le fichier {get_local_config_path().name}\n"
                "ou definis FIGMA_ACCESS_TOKEN sur la machine,\n"
                "ou configure un bridge MCP compatible.",
            )
            self.summary_var.set("Configuration Figma requise avant la generation.")
            self._set_output(_missing_access_message())
            return

        self._set_running_state(True)
        self.status_var.set("Generation en cours")
        self.summary_var.set(f"Lancement du mode {mode.value}...")
        self._set_output("Generation en cours, merci de patienter...\n")

        thread = threading.Thread(
            target=self._run_generation_job,
            args=(figma_url, Path(destination), mode, self.token_var.get().strip()),
            daemon=True,
        )
        thread.start()

    def _run_generation_job(self, figma_url: str, destination: Path, mode: OutputMode, token: str) -> None:
        try:
            previous_token = os.environ.get("FIGMA_ACCESS_TOKEN")
            if token:
                os.environ["FIGMA_ACCESS_TOKEN"] = token
            result = run_generation(GenerationOptions(figma_url=figma_url, out=destination, mode=mode))
            self._queue.put(("success", result))
        except Exception as exc:  # pragma: no cover - UI thread handoff
            self._queue.put(("error", _format_generation_error(str(exc))))
        finally:
            if token:
                if previous_token is None:
                    os.environ.pop("FIGMA_ACCESS_TOKEN", None)
                else:
                    os.environ["FIGMA_ACCESS_TOKEN"] = previous_token

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "success":
                    result = payload
                    self._last_output_dir = Path(result["outDir"])
                    self.status_var.set("Termine")
                    self.summary_var.set(
                        f"Generation {result['mode']} terminee. Rapport ecrit dans {Path(result['report']).name}."
                    )
                    self._set_output(json.dumps(result, indent=2, ensure_ascii=False))
                    self.open_folder_button.configure(state="normal")
                    self._set_running_state(False)
                elif kind == "error":
                    self.status_var.set("Erreur")
                    self.summary_var.set("La generation a echoue.")
                    self._set_output(str(payload))
                    self._set_running_state(False)
        except Empty:
            pass
        finally:
            self._root.after(150, self._poll_queue)

    def _set_running_state(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self._is_running = running
        self.url_entry.configure(state=state)
        self.destination_entry.configure(state=state)
        self.token_entry.configure(state=state)
        self.browse_button.configure(state=state)
        self.generate_hugo_button.configure(state=state)
        self.generate_static_button.configure(state=state)

    def _set_output(self, content: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", content.strip() + "\n")
        self.output_text.configure(state="disabled")

    def _open_output_dir(self) -> None:
        if not self._last_output_dir:
            return
        _open_directory(self._last_output_dir)


def _open_directory(path: Path) -> None:
    resolved = path.resolve()
    if os.name == "nt":
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return
    if os.name == "posix":
        command = ["open" if sys.platform == "darwin" else "xdg-open", str(resolved)]
        subprocess.Popen(command)
        return
    raise RuntimeError(f"Unsupported platform for opening directories: {os.name}")


def _has_figma_access(token_override: str | None = None) -> bool:
    if token_override and token_override.strip():
        return True
    if get_local_figma_token():
        return True
    if os.getenv("FIGMA_MCP_URL") or os.getenv("FIGMA_MCP_COMMAND"):
        return True
    return False


def _missing_access_message() -> str:
    return (
        "Generation impossible: aucun acces Figma n'est configure.\n\n"
        "Solutions:\n"
        "1. colle un personal access token dans le champ \"Token Figma\"\n"
        f"2. ou ajoute-le dans {get_local_config_path().name}\n"
        "3. ou definis FIGMA_ACCESS_TOKEN dans l'environnement\n"
        "4. ou configure FIGMA_MCP_URL / FIGMA_MCP_COMMAND pour un bridge MCP\n\n"
        "Le token REST Figma peut etre genere depuis les reglages de securite Figma."
    )


def _format_generation_error(message: str) -> str:
    if "Unable to extract Figma data" in message or "FIGMA_ACCESS_TOKEN" in message:
        return _missing_access_message() + "\n\nDetail technique:\n" + message
    return message


def launch_app() -> None:
    Figma2HugoGUI().run()


def main() -> None:
    launch_app()


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from figma2hugo import gui_presenter
from figma2hugo.config import OutputMode
from figma2hugo.local_config import get_local_config_path, get_local_figma_token
from figma2hugo.progress import (
    format_progress_event as _format_progress_event,
)
from figma2hugo.progress import (
    progress_status_label as _progress_status_label,
)
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
        self._root.geometry("820x620")
        self._root.minsize(760, 560)
        self._root.configure(bg="#f3efe7")

        self._queue: Queue[tuple[str, Any]] = Queue()
        self._is_running = False
        self._last_output_dir: Path | None = None

        self.url_vars: list[Any] = [tk.StringVar()]
        self.url_entries: list[Any] = []
        self.url_add_buttons: list[Any] = []
        self.url_remove_buttons: list[Any] = []
        self.destination_var = tk.StringVar(value=str(Path.cwd() / "site"))
        self.token_var = tk.StringVar(value=get_local_figma_token() or "")
        self.token_visible_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Pret")
        self.summary_var = tk.StringVar(
            value="Saisis une ou plusieurs URLs Figma et un dossier de destination."
        )
        self.selection_hint_var = tk.StringVar()

        self._build_styles()
        self._build_layout(ScrolledText)
        self._bind_dynamic_inputs()
        self._refresh_input_feedback()
        self._poll_queue()

    def run(self) -> None:
        self._root.mainloop()

    def _build_styles(self) -> None:
        style = self._ttk.Style()
        style.theme_use("clam")
        style.configure("App.TFrame", background="#f3efe7")
        style.configure("Card.TFrame", background="#fffaf2", relief="flat")
        style.configure(
            "Header.TLabel",
            background="#f3efe7",
            foreground="#1d2a2f",
            font=("Segoe UI", 23, "bold"),
        )
        style.configure(
            "Body.TLabel", background="#f3efe7", foreground="#4b5b61", font=("Segoe UI", 10)
        )
        style.configure(
            "CardTitle.TLabel",
            background="#fffaf2",
            foreground="#1d2a2f",
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "CardBody.TLabel", background="#fffaf2", foreground="#4b5b61", font=("Segoe UI", 10)
        )
        style.configure(
            "Field.TLabel",
            background="#fffaf2",
            foreground="#243238",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background="#d9efe2",
            foreground="#0d5c3b",
            font=("Segoe UI", 10, "bold"),
            padding=(10, 6),
        )
        style.configure(
            "Hint.TLabel", background="#fffaf2", foreground="#5a676e", font=("Segoe UI", 9)
        )
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 10))
        style.configure(
            "Link.TCheckbutton", background="#fffaf2", foreground="#324349", font=("Segoe UI", 9)
        )

    def _build_layout(self, scrolled_text_class: type) -> None:
        root = self._root
        tk = self._tk
        ttk = self._ttk

        scroll_host = ttk.Frame(root, style="App.TFrame")
        scroll_host.pack(fill="both", expand=True)
        scroll_host.columnconfigure(0, weight=1)
        scroll_host.rowconfigure(0, weight=1)

        self.shell_canvas = tk.Canvas(
            scroll_host,
            background="#f3efe7",
            highlightthickness=0,
            borderwidth=0,
        )
        self.shell_canvas.grid(row=0, column=0, sticky="nsew")
        self.shell_scrollbar = ttk.Scrollbar(
            scroll_host, orient="vertical", command=self.shell_canvas.yview
        )
        self.shell_scrollbar.grid(row=0, column=1, sticky="ns")
        self.shell_canvas.configure(yscrollcommand=self.shell_scrollbar.set)

        shell = ttk.Frame(self.shell_canvas, style="App.TFrame", padding=24)
        self.shell_frame = shell
        self._shell_window = self.shell_canvas.create_window((0, 0), window=shell, anchor="nw")
        shell.bind("<Configure>", self._on_shell_configure)
        self.shell_canvas.bind("<Configure>", self._on_shell_canvas_configure)
        self._bind_shell_scroll(shell)

        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        hero = ttk.Frame(shell, style="App.TFrame")
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)

        ttk.Label(hero, text="figma2hugo", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text="Une ou plusieurs URLs Figma, un dossier cible, puis lancement de la generation.",
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(hero, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=1, rowspan=2, sticky="e"
        )

        form_card = ttk.Frame(shell, style="Card.TFrame", padding=20)
        form_card.grid(row=1, column=0, sticky="ew", pady=(18, 14))
        form_card.columnconfigure(0, weight=1)
        form_card.columnconfigure(1, weight=0)

        ttk.Label(form_card, text="Generation", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            form_card,
            text=(
                "Le mode Hugo gere aussi le multi-pages. Le statique reste disponible "
                "pour une seule URL."
            ),
            style="CardBody.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))

        ttk.Label(form_card, text="URLs Figma", style="Field.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )
        self.url_rows_frame = ttk.Frame(form_card, style="Card.TFrame")
        self.url_rows_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 14))
        self.url_rows_frame.columnconfigure(0, weight=1)
        self._render_url_rows()
        ttk.Label(
            form_card,
            textvariable=self.selection_hint_var,
            style="Hint.TLabel",
            justify="left",
            wraplength=620,
        ).grid(row=4, column=0, columnspan=2, sticky="w")

        ttk.Label(form_card, text="Dossier de destination", style="Field.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(12, 0)
        )
        self.destination_entry = ttk.Entry(
            form_card, textvariable=self.destination_var, font=("Segoe UI", 10)
        )
        self.destination_entry.grid(
            row=6, column=0, sticky="ew", pady=(6, 0), ipady=6, padx=(0, 10)
        )
        self.browse_button = ttk.Button(
            form_card, text="Parcourir", style="Secondary.TButton", command=self._choose_directory
        )
        self.browse_button.grid(row=6, column=1, sticky="ew")

        ttk.Label(
            form_card,
            text="Les assets sont exportes en mode lightweight pour reduire le poids des rasters.",
            style="CardBody.TLabel",
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(14, 0))

        ttk.Label(form_card, text="Token Figma", style="Field.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(14, 0)
        )
        self.token_entry = ttk.Entry(
            form_card, textvariable=self.token_var, font=("Consolas", 10), show="*"
        )
        self.token_entry.grid(row=9, column=0, sticky="ew", pady=(6, 0), ipady=6, padx=(0, 10))
        self.toggle_token_button = ttk.Checkbutton(
            form_card,
            text="Afficher",
            variable=self.token_visible_var,
            style="Link.TCheckbutton",
            command=self._toggle_token_visibility,
        )
        self.toggle_token_button.grid(row=9, column=1, sticky="e")
        ttk.Label(
            form_card,
            text=(
                f"Optionnel si present dans {get_local_config_path().name}, "
                "FIGMA_ACCESS_TOKEN, ou un bridge MCP."
            ),
            style="CardBody.TLabel",
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(6, 0))

        actions = ttk.Frame(form_card, style="Card.TFrame")
        actions.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(18, 0))
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

        self.progressbar = ttk.Progressbar(form_card, mode="indeterminate")
        self.progressbar.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        output_card = ttk.Frame(shell, style="Card.TFrame", padding=20)
        output_card.grid(row=2, column=0, sticky="nsew")
        output_card.columnconfigure(0, weight=1)
        output_card.rowconfigure(2, weight=1)

        ttk.Label(output_card, text="Retour", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
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
        self._set_running_state(False)

    def _choose_directory(self) -> None:
        from tkinter import filedialog

        directory = filedialog.askdirectory(
            initialdir=self.destination_var.get() or str(Path.cwd())
        )
        if directory:
            self.destination_var.set(directory)

    def _start_generation(self, mode: OutputMode) -> None:
        from tkinter import messagebox

        if self._is_running:
            return

        figma_urls = _clean_figma_urls(self.url_vars)
        destination = self.destination_var.get().strip()
        if not figma_urls:
            messagebox.showerror("URL manquante", "Saisis au moins une URL Figma.")
            return
        if not destination:
            messagebox.showerror("Destination manquante", "Choisis un dossier de destination.")
            return
        if mode is OutputMode.STATIC and len(figma_urls) > 1:
            messagebox.showerror(
                "Mode indisponible",
                "L'export statique ne gere qu'une seule URL.\n"
                "Utilise le mode Hugo pour plusieurs pages.",
            )
            return
        if not _has_figma_access(self.token_var.get()):
            messagebox.showerror(
                "Acces Figma manquant",
                "Aucun acces Figma n'est configure.\n\n"
                'Renseigne un token dans le champ "Token Figma"\n'
                f"ou dans le fichier {get_local_config_path().name}\n"
                "ou definis FIGMA_ACCESS_TOKEN sur la machine,\n"
                "ou configure un bridge MCP compatible.",
            )
            self.summary_var.set("Configuration Figma requise avant la generation.")
            self._set_output(_missing_access_message())
            return

        self._set_running_state(True)
        self.status_var.set("Generation en cours")
        self.summary_var.set(_generation_launch_summary(mode, len(figma_urls)))
        self._set_output(
            _format_generation_start(
                figma_urls, Path(destination), mode, self.token_var.get().strip()
            )
        )
        self._append_output("\nGeneration en cours, merci de patienter...\n")

        thread = threading.Thread(
            target=self._run_generation_job,
            args=(figma_urls, Path(destination), mode, self.token_var.get().strip()),
            daemon=True,
        )
        thread.start()

    def _run_generation_job(
        self, figma_urls: list[str], destination: Path, mode: OutputMode, token: str
    ) -> None:
        try:
            previous_token = os.environ.get("FIGMA_ACCESS_TOKEN")
            if token:
                os.environ["FIGMA_ACCESS_TOKEN"] = token
            result = run_generation(
                GenerationOptions(
                    figma_url=figma_urls[0],
                    figma_urls=tuple(figma_urls),
                    out=destination,
                    mode=mode,
                ),
                progress_callback=self._enqueue_progress_event,
            )
            self._queue.put(("success", result))
        except Exception as exc:  # pragma: no cover - UI thread handoff
            self._queue.put(("error", _describe_generation_error(str(exc))))
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
                        f"Generation {result['mode']} terminee. Rapport ecrit dans "
                        f"{Path(result['report']).name}."
                    )
                    self._append_output("\n" + _format_generation_success(result))
                    self.open_folder_button.configure(state="normal")
                    self._set_running_state(False)
                elif kind == "progress":
                    progress = (
                        payload
                        if isinstance(payload, dict)
                        else {"stage": "progress", "message": str(payload)}
                    )
                    self.status_var.set(_progress_status_label(str(progress.get("stage", ""))))
                    self.summary_var.set(str(progress.get("message", "Generation en cours.")))
                    self._append_output(_format_progress_event(progress))
                elif kind == "error":
                    error_payload = (
                        payload
                        if isinstance(payload, dict)
                        else _describe_generation_error(str(payload))
                    )
                    self.status_var.set(str(error_payload.get("status", "Erreur")))
                    self.summary_var.set(
                        str(error_payload.get("summary", "La generation a echoue."))
                    )
                    self._append_output("\n" + str(error_payload.get("details", payload)))
                    self._set_running_state(False)
        except Empty:
            pass
        finally:
            self._root.after(150, self._poll_queue)

    def _set_running_state(self, running: bool) -> None:
        figma_urls = _clean_figma_urls(self.url_vars)
        states = _control_states(figma_urls, running=running)
        self._is_running = running
        for entry in self.url_entries:
            entry.configure(state=states.default)
        for button in self.url_add_buttons:
            button.configure(state=states.default)
        for button in self.url_remove_buttons:
            button.configure(state=states.default)
        if hasattr(self, "destination_entry"):
            self.destination_entry.configure(state=states.default)
        if hasattr(self, "token_entry"):
            self.token_entry.configure(state=states.default)
        if hasattr(self, "toggle_token_button"):
            self.toggle_token_button.configure(state=states.default)
        if hasattr(self, "browse_button"):
            self.browse_button.configure(state=states.default)
        if hasattr(self, "generate_hugo_button"):
            self.generate_hugo_button.configure(state=states.default)
        if hasattr(self, "generate_static_button"):
            self.generate_static_button.configure(state=states.static_button)
        if hasattr(self, "progressbar"):
            if states.progress_running:
                self.progressbar.start(10)
            else:
                self.progressbar.stop()

    def _render_url_rows(self) -> None:
        ttk = self._ttk
        for child in self.url_rows_frame.winfo_children():
            child.destroy()
        self.url_entries = []
        self.url_add_buttons = []
        self.url_remove_buttons = []

        for index, variable in enumerate(self.url_vars):
            row = ttk.Frame(self.url_rows_frame, style="Card.TFrame")
            row.grid(
                row=index,
                column=0,
                sticky="ew",
                pady=(0, 8 if index < len(self.url_vars) - 1 else 0),
            )
            row.columnconfigure(0, weight=1)

            entry = ttk.Entry(row, textvariable=variable, font=("Segoe UI", 10))
            entry.grid(row=0, column=0, sticky="ew", ipady=6)
            add_button = ttk.Button(
                row,
                text="+",
                width=3,
                style="Secondary.TButton",
                command=self._add_url_row,
            )
            add_button.grid(row=0, column=1, padx=(8, 4))
            remove_button = ttk.Button(
                row,
                text="-",
                width=3,
                style="Secondary.TButton",
                command=lambda current=index: self._remove_url_row(current),
            )
            remove_button.grid(row=0, column=2)

            self.url_entries.append(entry)
            self.url_add_buttons.append(add_button)
            self.url_remove_buttons.append(remove_button)

        self._set_running_state(self._is_running)
        self._refresh_input_feedback()

    def _add_url_row(self) -> None:
        self.url_vars.append(self._tk.StringVar())
        self._bind_url_var(self.url_vars[-1])
        self._render_url_rows()
        if self.url_entries:
            self.url_entries[-1].focus_set()

    def _remove_url_row(self, index: int) -> None:
        if len(self.url_vars) <= 1:
            return
        del self.url_vars[index]
        self._render_url_rows()
        if self.url_entries:
            self.url_entries[min(index, len(self.url_entries) - 1)].focus_set()

    def _set_output(self, content: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", content.strip() + "\n")
        self.output_text.configure(state="disabled")
        self.output_text.see("end")

    def _append_output(self, content: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.insert("end", content.rstrip() + "\n")
        self.output_text.configure(state="disabled")
        self.output_text.see("end")

    def _open_output_dir(self) -> None:
        if not self._last_output_dir:
            return
        _open_directory(self._last_output_dir)

    def _toggle_token_visibility(self) -> None:
        self.token_entry.configure(show="" if self.token_visible_var.get() else "*")

    def _enqueue_progress_event(self, payload: dict[str, Any]) -> None:
        self._queue.put(("progress", payload))

    def _on_shell_configure(self, _event: Any) -> None:
        self.shell_canvas.configure(scrollregion=self.shell_canvas.bbox("all"))

    def _on_shell_canvas_configure(self, event: Any) -> None:
        self.shell_canvas.itemconfigure(self._shell_window, width=event.width)

    def _bind_shell_scroll(self, shell: Any) -> None:
        del shell
        self._root.bind_all("<MouseWheel>", self._on_shell_mousewheel, add="+")
        self._root.bind_all("<Button-4>", self._on_shell_mousewheel_linux, add="+")
        self._root.bind_all("<Button-5>", self._on_shell_mousewheel_linux, add="+")

    def _on_shell_mousewheel(self, event: Any) -> str | None:
        if not self._should_route_shell_scroll(event):
            return None
        raw_delta = int(getattr(event, "delta", 0) or 0)
        if not raw_delta:
            return None
        steps = max(1, abs(raw_delta) // 120)
        direction = -1 if raw_delta > 0 else 1
        self.shell_canvas.yview_scroll(direction * steps, "units")
        return "break"

    def _on_shell_mousewheel_linux(self, event: Any) -> str | None:
        if not self._should_route_shell_scroll(event):
            return None
        step = -1 if getattr(event, "num", 0) == 4 else 1
        self.shell_canvas.yview_scroll(step, "units")
        return "break"

    def _should_route_shell_scroll(self, event: Any) -> bool:
        widget = getattr(event, "widget", None)
        if widget is None:
            return False
        if self._is_descendant_widget(widget, self.output_text):
            return False
        return self._is_descendant_widget(widget, self.shell_frame) or self._is_descendant_widget(
            widget, self.shell_canvas
        )

    def _is_descendant_widget(self, widget: Any, ancestor: Any) -> bool:
        if widget is ancestor:
            return True
        current = widget
        while current is not None:
            if str(current) == str(ancestor):
                return True
            try:
                parent_name = current.winfo_parent()
            except Exception:
                return False
            if not parent_name:
                return False
            try:
                current = current.nametowidget(parent_name)
            except Exception:
                return False
        return False

    def _bind_dynamic_inputs(self) -> None:
        self.destination_var.trace_add("write", lambda *_args: self._refresh_input_feedback())
        self.token_var.trace_add("write", lambda *_args: self._refresh_input_feedback())
        for variable in self.url_vars:
            self._bind_url_var(variable)

    def _bind_url_var(self, variable: Any) -> None:
        if hasattr(variable, "trace_add"):
            variable.trace_add("write", lambda *_args: self._refresh_input_feedback())

    def _refresh_input_feedback(self) -> None:
        figma_urls = _clean_figma_urls(self.url_vars)
        self.selection_hint_var.set(_selection_hint_message(figma_urls))
        if not self._is_running and hasattr(self, "generate_static_button"):
            self.generate_static_button.configure(state=self._static_button_state(running=False))

    def _static_button_state(self, *, running: bool) -> str:
        figma_urls = _clean_figma_urls(self.url_vars)
        return _control_states(figma_urls, running=running).static_button


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
    return gui_presenter.has_figma_access(
        token_override,
        local_token=get_local_figma_token(),
        mcp_url=os.getenv("FIGMA_MCP_URL"),
        mcp_command=os.getenv("FIGMA_MCP_COMMAND"),
    )


def _missing_access_message() -> str:
    return gui_presenter.missing_access_message(get_local_config_path().name)


def _clean_figma_urls(values: list[Any]) -> list[str]:
    return gui_presenter.clean_figma_urls(values)


def _supports_static_mode(figma_urls: list[str]) -> bool:
    return gui_presenter.supports_static_mode(figma_urls)


def _control_states(figma_urls: list[str], *, running: bool) -> gui_presenter.GuiControlStates:
    return gui_presenter.control_states(figma_urls, running=running)


def _figma_access_source(token_override: str | None = None) -> str:
    return gui_presenter.figma_access_source(
        token_override,
        local_token=get_local_figma_token(),
        local_config_name=get_local_config_path().name,
        env_token=os.getenv("FIGMA_ACCESS_TOKEN"),
        env_token_alt=os.getenv("FIGMA_TOKEN"),
        mcp_url=os.getenv("FIGMA_MCP_URL"),
        mcp_command=os.getenv("FIGMA_MCP_COMMAND"),
    )


def _selection_hint_message(figma_urls: list[str]) -> str:
    return gui_presenter.selection_hint_message(figma_urls)


def _generation_launch_summary(mode: OutputMode, figma_url_count: int) -> str:
    return gui_presenter.generation_launch_summary(mode, figma_url_count)


def _format_generation_start(
    figma_urls: list[str],
    destination: Path,
    mode: OutputMode,
    token_override: str | None,
) -> str:
    return gui_presenter.format_generation_start(
        figma_urls,
        destination,
        mode,
        access_source=_figma_access_source(token_override),
    )


def _format_generation_success(result: dict[str, Any]) -> str:
    return gui_presenter.format_generation_success(result)


def _format_generation_error(message: str) -> str:
    return gui_presenter.format_generation_error(
        message,
        access_message=_missing_access_message(),
    )


def _describe_generation_error(message: str) -> dict[str, str]:
    return gui_presenter.describe_generation_error(
        message,
        access_message=_missing_access_message(),
    )


def launch_app() -> None:
    Figma2HugoGUI().run()


def main() -> None:
    launch_app()


if __name__ == "__main__":
    main()

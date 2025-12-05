import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import io
from contextlib import redirect_stdout
import random
import os

from PIL import Image
import sim

sort_state = {}
comp_name_to_id = {}


class SimpleTooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)

    def _enter(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#111111",
            foreground="#ffffff",
            relief="solid",
            borderwidth=1,
            padx=4,
            pady=2,
            font=("Segoe UI", 9)
        )
        label.pack(ipadx=1)

    def _leave(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Football Career Sim")
        self.geometry("1300x750")

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.home_tab = None
        self.continent_tab = None
        self.country_tab = None
        self.league_tab = None
        self.team_tab = None
        self.comp_detail_tab = None

        self.table_tree = None
        self.output_box = None
        self.comp_select = None
        self.season_select = None

        self.current_team_id = None
        self._team_logo_image = None
        self._trophy_images = []
        self._comp_logo_image = None

        self._continent_map = {}  # display_name -> continent_folder
        self._nation_key_map = {}  # (cont_folder, nation_id) -> nation_obj

        self.current_continent_folder = None
        self.current_country_cont_folder = None
        self.current_country_nation_id = None
        self.current_competition_id = None

        self._build_header()

        sim.load_world()

        self._build_tabs()

        self._update_season_selector()
        self._populate_competitions()
        self._update_table_for_competition()

    # ---------- Helpers ----------

    @staticmethod
    def _slug(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    def _to_stars(self, value):
        try:
            v = int(value)
        except (ValueError, TypeError):
            return "N/A"
        if v <= 0:
            return "—"
        if v > 100:
            v = 100
        bucket = (v - 1) // 10  # 0..9
        if bucket >= 8:
            stars = 5.0
        else:
            stars = 0.5 + bucket * 0.5
        full = int(stars)
        half = (stars - full) >= 0.25
        return "★" * full + ("☆" if half else "")

    # ---------- Header ----------

    def _build_header(self):
        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        for i in range(10):
            header.grid_columnconfigure(i, weight=0)
        header.grid_columnconfigure(10, weight=1)

        ctk.CTkLabel(header, text="Seasons").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.seasons_entry = ctk.CTkEntry(header, width=60)
        self.seasons_entry.insert(0, "1")
        self.seasons_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(header, text="Seed").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.seed_entry = ctk.CTkEntry(header, width=80)
        self.seed_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        self.fixtures_var = tk.BooleanVar(value=False)
        fixtures_check = ctk.CTkCheckBox(header, text="Show fixtures", variable=self.fixtures_var)
        fixtures_check.grid(row=0, column=4, padx=5, pady=5, sticky="w")

        run_button = ctk.CTkButton(header, text="Run Simulation", command=self._run_simulation)
        run_button.grid(row=0, column=5, padx=10, pady=5, sticky="w")

        clear_button = ctk.CTkButton(header, text="Clear Output", command=self._clear_output)
        clear_button.grid(row=0, column=6, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(header, text="Season view").grid(row=0, column=7, padx=5, pady=5, sticky="e")
        self.season_select = ctk.CTkComboBox(
            header,
            values=["No seasons"],
            command=lambda _: self._update_table_for_competition(),
            width=140
        )
        self.season_select.set("No seasons")
        self.season_select.grid(row=0, column=8, padx=5, pady=5, sticky="e")

    # ---------- Tabs ----------

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.home_tab = ctk.CTkFrame(self.notebook)
        self.continent_tab = ctk.CTkFrame(self.notebook)
        self.country_tab = ctk.CTkFrame(self.notebook)
        self.league_tab = ctk.CTkFrame(self.notebook)
        self.team_tab = ctk.CTkFrame(self.notebook)
        self.comp_detail_tab = ctk.CTkFrame(self.notebook)

        self.notebook.add(self.home_tab, text="Home")
        self.notebook.add(self.continent_tab, text="Continent")
        self.notebook.add(self.country_tab, text="Country")
        self.notebook.add(self.league_tab, text="Leagues")
        self.notebook.add(self.team_tab, text="Team")
        self.notebook.add(self.comp_detail_tab, text="Competition")

        self._build_home_tab()

        # Leagues tab
        self.league_tab.rowconfigure(0, weight=1)
        self.league_tab.columnconfigure(0, weight=1)

        paned = tk.PanedWindow(self.league_tab, orient=tk.HORIZONTAL, sashwidth=6, sashrelief="raised")
        paned.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        left_container = ctk.CTkFrame(paned)
        right_container = ctk.CTkFrame(paned)

        left_container.rowconfigure(1, weight=1)
        left_container.columnconfigure(0, weight=1)

        right_container.rowconfigure(0, weight=1)
        right_container.columnconfigure(0, weight=1)

        paned.add(left_container, stretch="always")
        right_container.configure(width=350)
        paned.add(right_container)

        top_table_bar = ctk.CTkFrame(left_container, fg_color="transparent")
        top_table_bar.grid(row=0, column=0, sticky="ew", pady=(5, 0))
        top_table_bar.grid_columnconfigure(1, weight=1)
        top_table_bar.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(top_table_bar, text="Competition").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.comp_select = ctk.CTkComboBox(
            top_table_bar,
            values=[],
            command=lambda _: self._update_table_for_competition()
        )
        self.comp_select.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        view_comp_btn = ctk.CTkButton(
            top_table_bar,
            text="Open competition view",
            width=150,
            command=self._open_selected_competition
        )
        view_comp_btn.grid(row=0, column=2, padx=5, pady=5, sticky="e")

        tree_container = ctk.CTkFrame(left_container)
        tree_container.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        tree_container.rowconfigure(0, weight=1)
        tree_container.columnconfigure(0, weight=1)

        columns = ("Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts")
        self.columns = columns
        self.table_tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=18)

        for col in columns:
            anchor = "center" if col != "Team" else "w"
            width = 60
            if col == "Team":
                width = 230
            self.table_tree.heading(col, text=col, command=lambda c=col: self._sort_table(c))
            self.table_tree.column(col, width=width, anchor=anchor)

        self.table_tree.grid(row=0, column=0, sticky="nsew")

        table_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.table_tree.yview)
        table_scroll.grid(row=0, column=1, sticky="ns")
        self.table_tree.configure(yscrollcommand=table_scroll.set)

        self.table_tree.bind("<Double-1>", self._on_tree_double_click)

        self.output_box = ctk.CTkTextbox(right_container, wrap="word")
        self.output_box.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.output_box.configure(state="disabled")

        self._build_empty_team_tab()
        self._build_empty_comp_tab()

    # ---------- Home tab ----------

    def _build_home_tab(self):
        for w in self.home_tab.winfo_children():
            w.destroy()

        self.home_tab.rowconfigure(1, weight=1)
        self.home_tab.columnconfigure(0, weight=1)
        self.home_tab.columnconfigure(1, weight=1)
        self.home_tab.columnconfigure(2, weight=1)

        # Build continent->folder and nation maps
        self._continent_map.clear()
        self._nation_key_map.clear()

        folder_keys = list(sim.NATIONS_BY_CONTINENT.keys())
        folder_slugs = {fk: self._slug(fk) for fk in folder_keys}

        continent_rows = []
        for c in sim.CONTINENTS:
            name = c.get("continentName", "Unknown")
            rep_val = c.get("reputation", c.get("continentReputation", 0))
            c_slug = self._slug(name)
            folder_match = None
            for fk, fslug in folder_slugs.items():
                if fslug == c_slug:
                    folder_match = fk
                    break
            if folder_match is None:
                continue
            self._continent_map[name] = folder_match
            continent_rows.append((rep_val or 0, name, folder_match))

        continent_rows.sort(key=lambda x: x[0], reverse=True)

        # Countries rows: (rep, label, cont_folder, nation_id, nation_obj)
        country_rows = []
        for cont_folder, nations in sim.NATIONS_BY_CONTINENT.items():
            for n in nations:
                nid = n.get("nationId")
                name = n.get("nationName", f"Nation {nid}")
                rep_val = n.get("reputation", n.get("nationReputation", 0)) or 0
                label = name
                country_rows.append((rep_val, label, cont_folder, nid, n))
                self._nation_key_map[(cont_folder, nid)] = n
        country_rows.sort(key=lambda x: x[0], reverse=True)

        # Competitions rows (all, from both continental + domestic)
        comp_info = {}
        # continental-level comps
        for cont_folder, comps in sim.CONTINENT_LEVEL_COMPS.items():
            for comp in comps:
                cid = comp.get("compId")
                cname = comp.get("compName", f"Comp {cid}")
                rep_val = comp.get("reputation", comp.get("compReputation", 0)) or 0
                if cid is None:
                    continue
                if cid not in comp_info or rep_val > comp_info[cid]["rep"]:
                    comp_info[cid] = {"name": cname, "rep": rep_val}
        # nation-level comps
        for comps in sim.NATION_COMPS.values():
            for comp in comps:
                cid = comp.get("compId")
                cname = comp.get("compName", f"Comp {cid}")
                rep_val = comp.get("reputation", comp.get("compReputation", 0)) or 0
                if cid is None:
                    continue
                if cid not in comp_info or rep_val > comp_info[cid]["rep"]:
                    comp_info[cid] = {"name": cname, "rep": rep_val}

        comp_rows = []
        for cid, info in comp_info.items():
            comp_rows.append((info["rep"], info["name"], cid))
        comp_rows.sort(key=lambda x: x[0], reverse=True)

        # Left: Continents
        left_frame = ctk.CTkFrame(self.home_tab)
        left_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(10, 5), pady=10)
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left_frame,
            text="Continents",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        cont_list = ctk.CTkScrollableFrame(left_frame)
        cont_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        for rep_val, name, folder in continent_rows:
            stars = self._to_stars(rep_val)
            btn = ctk.CTkButton(
                cont_list,
                text=f"{name}   {stars}",
                command=lambda f=folder: self._open_continent_tab(f),
                height=32
            )
            btn.pack(fill="x", padx=4, pady=3)

        # Middle: Countries
        mid_frame = ctk.CTkFrame(self.home_tab)
        mid_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=5, pady=10)
        mid_frame.rowconfigure(1, weight=1)
        mid_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            mid_frame,
            text="Countries",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        country_list = ctk.CTkScrollableFrame(mid_frame)
        country_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        for rep_val, label, cont_folder, nid, nobj in country_rows:
            stars = self._to_stars(rep_val)
            btn = ctk.CTkButton(
                country_list,
                text=f"{label}   {stars}",
                command=lambda cf=cont_folder, nnid=nid: self._open_country_tab(cf, nnid),
                height=30
            )
            btn.pack(fill="x", padx=4, pady=2)

        # Right: Competitions
        right_frame = ctk.CTkFrame(self.home_tab)
        right_frame.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(5, 10), pady=10)
        right_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right_frame,
            text="Competitions",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        comp_list = ctk.CTkScrollableFrame(right_frame)
        comp_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        for rep_val, name, cid in comp_rows:
            stars = self._to_stars(rep_val)
            btn = ctk.CTkButton(
                comp_list,
                text=f"{name}   {stars}",
                command=lambda cc=cid: self._on_select_competition_from_home(cc),
                height=30
            )
            btn.pack(fill="x", padx=4, pady=2)

    # ---------- Continent tab ----------

    def _open_continent_tab(self, cont_folder):
        for w in self.continent_tab.winfo_children():
            w.destroy()

        self.current_continent_folder = cont_folder

        self.continent_tab.rowconfigure(1, weight=1)
        self.continent_tab.columnconfigure(0, weight=1)
        self.continent_tab.columnconfigure(1, weight=1)
        self.continent_tab.columnconfigure(2, weight=1)

        # Find continent object
        cont_obj = None
        cont_name = cont_folder.title()
        rep_val = 0
        folder_slug = self._slug(cont_folder)
        for c in sim.CONTINENTS:
            name = c.get("continentName", "Unknown")
            slug = self._slug(name)
            if slug == folder_slug:
                cont_obj = c
                cont_name = name
                rep_val = c.get("reputation", c.get("continentReputation", 0)) or 0
                break

        stars = self._to_stars(rep_val)

        top_label = ctk.CTkLabel(
            self.continent_tab,
            text=f"{cont_name}   {stars}",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        top_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        # 3 columns: countries, domestic comps, continental comps
        # Countries
        countries_frame = ctk.CTkFrame(self.continent_tab)
        countries_frame.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=10)
        countries_frame.rowconfigure(1, weight=1)
        countries_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            countries_frame,
            text=f"Countries in {cont_name}",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 4))

        c_list = ctk.CTkScrollableFrame(countries_frame)
        c_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)

        nations = sim.NATIONS_BY_CONTINENT.get(cont_folder, [])
        country_rows = []
        for n in nations:
            nid = n.get("nationId")
            name = n.get("nationName", f"Nation {nid}")
            rep_val = n.get("reputation", n.get("nationReputation", 0)) or 0
            country_rows.append((rep_val, name, nid, n))
        country_rows.sort(key=lambda x: x[0], reverse=True)

        for rep_val, name, nid, nobj in country_rows:
            stars = self._to_stars(rep_val)
            btn = ctk.CTkButton(
                c_list,
                text=f"{name}   {stars}",
                command=lambda nf=cont_folder, nid2=nid: self._open_country_tab(nf, nid2),
                height=30
            )
            btn.pack(fill="x", padx=4, pady=2)

        # Domestic competitions
        dom_frame = ctk.CTkFrame(self.continent_tab)
        dom_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=10)
        dom_frame.rowconfigure(1, weight=1)
        dom_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dom_frame,
            text="Domestic competitions",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 4))

        dom_list = ctk.CTkScrollableFrame(dom_frame)
        dom_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)

        dom_rows = []
        for (cf, nid), folder in sim.NATION_FOLDERS.items():
            if cf != cont_folder:
                continue
            nation_path = os.path.join(sim.DATA_DIR, cf, folder)
            comps = sim.NATION_COMPS.get(nation_path, [])
            for comp in comps:
                cid = comp.get("compId")
                cname = comp.get("compName", f"Comp {cid}")
                rep_val = comp.get("reputation", comp.get("compReputation", 0)) or 0
                if cid is None:
                    continue
                dom_rows.append((rep_val, cname, cid))
        dom_rows.sort(key=lambda x: x[0], reverse=True)

        for rep_val, cname, cid in dom_rows:
            stars = self._to_stars(rep_val)
            btn = ctk.CTkButton(
                dom_list,
                text=f"{cname}   {stars}",
                command=lambda cc=cid: self._open_competition_tab(cc),
                height=30
            )
            btn.pack(fill="x", padx=4, pady=2)

        # Continental competitions
        contc_frame = ctk.CTkFrame(self.continent_tab)
        contc_frame.grid(row=1, column=2, sticky="nsew", padx=(5, 10), pady=10)
        contc_frame.rowconfigure(1, weight=1)
        contc_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            contc_frame,
            text="Continental competitions",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 4))

        contc_list = ctk.CTkScrollableFrame(contc_frame)
        contc_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)

        contc_rows = []
        for comp in sim.CONTINENT_LEVEL_COMPS.get(cont_folder, []):
            cid = comp.get("compId")
            cname = comp.get("compName", f"Comp {cid}")
            rep_val = comp.get("reputation", comp.get("compReputation", 0)) or 0
            if cid is None:
                continue
            contc_rows.append((rep_val, cname, cid))
        contc_rows.sort(key=lambda x: x[0], reverse=True)

        for rep_val, cname, cid in contc_rows:
            stars = self._to_stars(rep_val)
            btn = ctk.CTkButton(
                contc_list,
                text=f"{cname}   {stars}",
                command=lambda cc=cid: self._open_competition_tab(cc),
                height=30
            )
            btn.pack(fill="x", padx=4, pady=2)

        self.notebook.select(self.continent_tab)

    # ---------- Country tab ----------

    def _open_country_tab(self, cont_folder, nation_id):
        for w in self.country_tab.winfo_children():
            w.destroy()

        self.current_country_cont_folder = cont_folder
        self.current_country_nation_id = nation_id

        self.country_tab.rowconfigure(2, weight=1)
        self.country_tab.columnconfigure(0, weight=1)
        self.country_tab.columnconfigure(1, weight=1)

        nations = sim.NATIONS_BY_CONTINENT.get(cont_folder, [])
        nobj = None
        for n in nations:
            if n.get("nationId") == nation_id:
                nobj = n
                break

        if nobj is None:
            label = ctk.CTkLabel(
                self.country_tab,
                text="Country not found.",
                font=ctk.CTkFont(size=16, weight="bold")
            )
            label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            self.notebook.select(self.country_tab)
            return

        name = nobj.get("nationName", f"Nation {nation_id}")
        rep_val = nobj.get("reputation", nobj.get("nationReputation", 0)) or 0
        rep_stars = self._to_stars(rep_val)

        top_frame = ctk.CTkFrame(self.country_tab, fg_color="transparent")
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        top_frame.grid_columnconfigure(0, weight=1)
        top_frame.grid_columnconfigure(1, weight=1)

        name_label = ctk.CTkLabel(
            top_frame,
            text=f"{name}   {rep_stars}",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        name_label.grid(row=0, column=0, sticky="w", padx=5, pady=(0, 2))

        # National team section (generic, uses whatever fields exist)
        nt_frame = ctk.CTkFrame(self.country_tab)
        nt_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))
        for i in range(4):
            nt_frame.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(nt_frame, text="National team", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 2)
        )

        # Try to read some generic rating fields if present
        nt_attack = nobj.get("ntAttack", nobj.get("attack", None))
        nt_mid = nobj.get("ntMidfield", nobj.get("midfield", None))
        nt_def = nobj.get("ntDefense", nobj.get("defense", None))
        nt_gk = nobj.get("ntGoalkeeping", nobj.get("goalkeeping", None))

        if any(v is not None for v in [nt_attack, nt_mid, nt_def, nt_gk]):
            if nt_attack is not None:
                ctk.CTkLabel(nt_frame, text=f"Attack: {nt_attack}").grid(
                    row=1, column=0, padx=5, pady=2, sticky="w"
                )
            if nt_mid is not None:
                ctk.CTkLabel(nt_frame, text=f"Midfield: {nt_mid}").grid(
                    row=1, column=1, padx=5, pady=2, sticky="w"
                )
            if nt_def is not None:
                ctk.CTkLabel(nt_frame, text=f"Defense: {nt_def}").grid(
                    row=1, column=2, padx=5, pady=2, sticky="w"
                )
            if nt_gk is not None:
                ctk.CTkLabel(nt_frame, text=f"GK: {nt_gk}").grid(
                    row=1, column=3, padx=5, pady=2, sticky="w"
                )
        else:
            ctk.CTkLabel(
                nt_frame,
                text="No national team ratings configured."
            ).grid(row=1, column=0, columnspan=4, padx=5, pady=2, sticky="w")

        # Lower area: left = domestic competitions, right = clubs
        lower_frame = ctk.CTkFrame(self.country_tab)
        lower_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(5, 10))
        lower_frame.rowconfigure(0, weight=1)
        lower_frame.columnconfigure(0, weight=1)
        lower_frame.columnconfigure(1, weight=1)

        # Domestic competitions
        dom_frame = ctk.CTkFrame(lower_frame)
        dom_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
        dom_frame.rowconfigure(1, weight=1)
        dom_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(dom_frame, text="Domestic competitions").grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0)
        )
        dom_list = ctk.CTkScrollableFrame(dom_frame)
        dom_list.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        dom_rows = []
        for (cf, nid), folder in sim.NATION_FOLDERS.items():
            if cf != cont_folder or nid != nation_id:
                continue
            nation_path = os.path.join(sim.DATA_DIR, cf, folder)
            comps = sim.NATION_COMPS.get(nation_path, [])
            for comp in comps:
                cid = comp.get("compId")
                cname = comp.get("compName", f"Comp {cid}")
                rep_val = comp.get("reputation", comp.get("compReputation", 0)) or 0
                if cid is None:
                    continue
                dom_rows.append((rep_val, cname, cid))
        dom_rows.sort(key=lambda x: x[0], reverse=True)

        for rep_val, cname, cid in dom_rows:
            stars = self._to_stars(rep_val)
            btn = ctk.CTkButton(
                dom_list,
                text=f"{cname}   {stars}",
                command=lambda cc=cid: self._open_competition_tab(cc),
                height=30
            )
            btn.pack(fill="x", padx=4, pady=2)

        # Clubs list in that country (by reputation)
        clubs_frame = ctk.CTkFrame(lower_frame)
        clubs_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        clubs_frame.rowconfigure(1, weight=1)
        clubs_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(clubs_frame, text="Clubs in this country").grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0)
        )
        clubs_list = ctk.CTkScrollableFrame(clubs_frame)
        clubs_list.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Collect unique clubs based on teamNationId
        clubs_map = {}
        for teams in sim.COMP_TEAMS.values():
            for t in teams:
                if t.get("teamNationId") != nation_id:
                    continue
                tid = t.get("teamId")
                if tid is None:
                    continue
                if tid not in clubs_map:
                    clubs_map[tid] = t

        clubs_rows = []
        for tid, t in clubs_map.items():
            rep = t.get("reputationFactor", 0)
            clubs_rows.append((rep, tid, t))
        clubs_rows.sort(key=lambda x: x[0], reverse=True)

        for rep, tid, t in clubs_rows:
            stars = self._to_stars(rep)
            name = t.get("teamName", f"Team {tid}")
            btn = ctk.CTkButton(
                clubs_list,
                text=f"{name}   {stars}",
                command=lambda team_id=tid: self._open_team_tab(team_id),
                height=28
            )
            btn.pack(fill="x", padx=4, pady=2)

        self.notebook.select(self.country_tab)

    # ---------- Empty placeholders ----------

    def _build_empty_team_tab(self):
        for w in self.team_tab.winfo_children():
            w.destroy()
        self.team_tab.rowconfigure(0, weight=1)
        self.team_tab.columnconfigure(0, weight=1)
        placeholder = ctk.CTkLabel(
            self.team_tab,
            text="No team selected.\nDouble-click a team in the league table.",
            justify="center",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        placeholder.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    def _build_empty_comp_tab(self):
        for w in self.comp_detail_tab.winfo_children():
            w.destroy()
        self.comp_detail_tab.rowconfigure(0, weight=1)
        self.comp_detail_tab.columnconfigure(0, weight=1)
        placeholder = ctk.CTkLabel(
            self.comp_detail_tab,
            text="No competition selected.\nUse 'Open competition view' or click a trophy icon.",
            justify="center",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        placeholder.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    # ---------- Season selector + league view ----------

    def _update_season_selector(self):
        total = len(sim.LEAGUE_HISTORY)
        if total == 0:
            self.season_select.configure(values=["No seasons"])
            self.season_select.set("No seasons")
        else:
            vals = [f"Season {i}" for i in range(1, total + 1)]
            self.season_select.configure(values=vals)
            current = self.season_select.get()
            if current not in vals:
                self.season_select.set(vals[-1])

    def _get_selected_season_index(self):
        label = self.season_select.get()
        if not label or not label.startswith("Season "):
            return None
        try:
            idx = int(label.split()[1]) - 1
        except ValueError:
            return None
        if idx < 0 or idx >= len(sim.LEAGUE_HISTORY):
            return None
        return idx

    def _populate_competitions(self):
        global comp_name_to_id
        comp_name_to_id.clear()
        names = []
        for cid in sorted(sim.COMP_TEAMS.keys()):
            if sim.COMP_FORMAT.get(cid) == 0:
                name = sim.COMP_NAME_LOOKUP.get(cid, f"Competition {cid}")
                comp_name_to_id[name] = cid
                names.append(name)
        if not names:
            self.comp_select.configure(values=["No leagues"])
            self.comp_select.set("No leagues")
        else:
            self.comp_select.configure(values=names)
            if self.comp_select.get() not in names:
                self.comp_select.set(names[0])

    def _update_table_for_competition(self):
        name = self.comp_select.get()
        if not name or name not in comp_name_to_id:
            for row in self.table_tree.get_children():
                self.table_tree.delete(row)
            return

        season_idx = self._get_selected_season_index()
        if season_idx is None:
            for row in self.table_tree.get_children():
                self.table_tree.delete(row)
            return

        league_results = sim.LEAGUE_HISTORY[season_idx]
        cid = comp_name_to_id[name]
        if cid not in league_results:
            for row in self.table_tree.get_children():
                self.table_tree.delete(row)
            return

        res = league_results[cid]
        table = res.get("table", [])

        for row in self.table_tree.get_children():
            self.table_tree.delete(row)

        for pos, row in enumerate(table, start=1):
            team_id = row.get("teamId")
            values = (
                pos,
                row["teamName"],
                row.get("played", 0),
                row.get("wins", 0),
                row.get("draws", 0),
                row.get("losses", 0),
                row.get("gf", 0),
                row.get("ga", 0),
                row.get("gd", 0),
                row.get("points", 0),
            )
            iid = str(team_id)
            self.table_tree.insert("", "end", iid=iid, values=values)

    def _sort_table(self, column):
        items = list(self.table_tree.get_children())
        if not items:
            return

        col_index = self.columns.index(column)
        ascending = sort_state.get(column, True)

        def conv(val):
            if column == "Team":
                return val
            try:
                return int(val)
            except ValueError:
                try:
                    return float(val)
                except ValueError:
                    return val

        data = []
        for iid in items:
            vals = self.table_tree.item(iid, "values")
            data.append((conv(vals[col_index]), iid, vals))

        data.sort(key=lambda x: x[0], reverse=not ascending)

        for index, (_, iid, _) in enumerate(data):
            self.table_tree.move(iid, "", index)

        sort_state[column] = not ascending

    def _on_tree_double_click(self, event):
        item = self.table_tree.focus()
        if not item:
            return
        try:
            team_id = int(item)
        except ValueError:
            return
        self.current_team_id = team_id
        self._open_team_tab(team_id)

    # ---------- Simulation ----------

    def _run_simulation(self):
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")

        # remember current tab
        current_tab_id = self.notebook.select()

        try:
            seasons = int(self.seasons_entry.get())
            if seasons <= 0:
                seasons = 1
        except ValueError:
            seasons = 1

        seed_text = self.seed_entry.get().strip()
        if seed_text:
            try:
                seed_val = int(seed_text)
                random.seed(seed_val)
                sim.random.seed(seed_val)
            except ValueError:
                pass

        show_fixtures = self.fixtures_var.get()

        for _ in range(seasons):
            buf = io.StringIO()
            with redirect_stdout(buf):
                sim.run_season(show_fixtures=show_fixtures, show_table=True, run_cups=True)
            text = buf.getvalue()
            season_header = f"\n======================== SEASON {sim.CURRENT_SEASON} ========================\n"
            self.output_box.insert("end", season_header + text + "\n")

        self.output_box.configure(state="disabled")

        # refresh core data-driven widgets
        self._update_season_selector()
        self._populate_competitions()
        self._update_table_for_competition()

        # rebuild home to reflect new reputations / histories
        self._build_home_tab()

        # refresh any open context pages (but restore tab afterwards)
        if self.current_continent_folder is not None:
            self._open_continent_tab(self.current_continent_folder)

        if (self.current_country_cont_folder is not None and
                self.current_country_nation_id is not None):
            self._open_country_tab(self.current_country_cont_folder,
                                   self.current_country_nation_id)

        if self.current_competition_id is not None:
            self._open_competition_tab(self.current_competition_id)

        if self.current_team_id is not None:
            self._open_team_tab(self.current_team_id)

        # go back to the tab the user was on
        self.notebook.select(current_tab_id)

    def _clear_output(self):
        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")

    # ---------- Trophies / history helpers ----------

    def _compute_trophies(self, team_id, team_obj, info):
        trophies = {}

        base = team_obj.get("trophies", {})
        if isinstance(base, dict):
            for cid_str, count in base.items():
                try:
                    cid = int(cid_str)
                    c = int(count)
                except (ValueError, TypeError):
                    continue
                trophies[cid] = trophies.get(cid, 0) + c

        records = info.get("records", [])
        for r in records:
            t = r.get("type")
            cid = r.get("compId")
            if cid is None:
                continue
            if t == "league":
                if r.get("position") == 1:
                    trophies[cid] = trophies.get(cid, 0) + 1
            elif t == "cup":
                if r.get("winner"):
                    trophies[cid] = trophies.get(cid, 0) + 1

        return trophies

    def _league_positions_by_season(self, info):
        positions_by_season = {}
        records = info.get("records", [])
        for r in records:
            if r.get("type") != "league":
                continue
            season = r.get("season")
            comp_id = r.get("compId")
            pos = r.get("position")
            if season is None or comp_id is None or pos is None:
                continue
            tier = sim.COMP_TIER.get(comp_id, 99)
            existing = positions_by_season.get(season)
            if existing is None or tier < existing["tier"]:
                positions_by_season[season] = {
                    "tier": tier,
                    "position": pos,
                    "compId": comp_id
                }
        return positions_by_season

    # ---------- Asset loading ----------

    def _load_logo_image(self, team_id, size=(64, 64)):
        self._team_logo_image = None
        try:
            path = os.path.join(sim.DATA_DIR, "europe", "germany", "logos", f"{team_id}.png")
            if os.path.exists(path):
                img = Image.open(path)
                self._team_logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        except Exception:
            self._team_logo_image = None

    def _load_comp_logo_image(self, comp_id, size=(72, 72)):
        self._comp_logo_image = None
        try:
            path = os.path.join(sim.DATA_DIR, "europe", "germany", "leaguelogos", f"{comp_id}.png")
            if os.path.exists(path):
                img = Image.open(path)
                self._comp_logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        except Exception:
            self._comp_logo_image = None

    def _load_trophy_image(self, comp_id, size=(32, 32)):
        try:
            path = os.path.join(sim.DATA_DIR, "europe", "germany", "trophies", f"{comp_id}.png")
            if os.path.exists(path):
                img = Image.open(path)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self._trophy_images.append(ctk_img)
                return ctk_img
        except Exception:
            return None
        return None

    # ---------- Competition view ----------

    def _open_selected_competition(self):
        name = self.comp_select.get()
        if not name or name not in comp_name_to_id:
            return
        cid = comp_name_to_id[name]
        self._open_competition_tab(cid)

    def _open_competition_tab(self, comp_id):
        for w in self.comp_detail_tab.winfo_children():
            w.destroy()
        self._comp_logo_image = None

        self.current_competition_id = comp_id

        comp_name = sim.COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
        self._load_comp_logo_image(comp_id, size=(72, 72))

        self.comp_detail_tab.rowconfigure(2, weight=1)
        self.comp_detail_tab.columnconfigure(0, weight=1)
        self.comp_detail_tab.columnconfigure(1, weight=1)

        top_frame = ctk.CTkFrame(self.comp_detail_tab, fg_color="transparent")
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        top_frame.grid_columnconfigure(1, weight=1)

        if self._comp_logo_image is not None:
            logo_label = ctk.CTkLabel(top_frame, image=self._comp_logo_image, text="")
            logo_label.grid(row=0, column=0, rowspan=2, padx=(0, 10), pady=0, sticky="w")

        name_label = ctk.CTkLabel(
            top_frame,
            text=comp_name,
            font=ctk.CTkFont(size=20, weight="bold")
        )
        name_label.grid(row=0, column=1, sticky="w", padx=5, pady=(0, 2))

        middle_frame = ctk.CTkFrame(self.comp_detail_tab)
        middle_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))
        for i in range(3):
            middle_frame.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(middle_frame, text="Past winners").grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0)
        )
        ctk.CTkLabel(middle_frame, text="Current table").grid(
            row=0, column=1, sticky="w", padx=5, pady=(5, 0)
        )
        ctk.CTkLabel(middle_frame, text="Teams by reputation / titles").grid(
            row=0, column=2, sticky="w", padx=5, pady=(5, 0)
        )

        bottom_frame = ctk.CTkFrame(self.comp_detail_tab)
        bottom_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(5, 10))
        bottom_frame.rowconfigure(0, weight=1)
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)
        bottom_frame.columnconfigure(2, weight=1)

        winners_box = ctk.CTkTextbox(bottom_frame, wrap="word")
        winners_box.grid(row=0, column=0, sticky="nsew", padx=(5, 5), pady=5)

        table_frame = ctk.CTkFrame(bottom_frame)
        table_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 5), pady=5)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        comp_table = ttk.Treeview(
            table_frame,
            columns=("Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"),
            show="headings",
            height=16
        )
        for col in ("Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"):
            anchor = "center" if col != "Team" else "w"
            width = 60
            if col == "Team":
                width = 180
            comp_table.heading(col, text=col)
            comp_table.column(col, width=width, anchor=anchor)
        comp_table.grid(row=0, column=0, sticky="nsew")
        comp_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=comp_table.yview)
        comp_scroll.grid(row=0, column=1, sticky="ns")
        comp_table.configure(yscrollcommand=comp_scroll.set)

        rep_box = ctk.CTkTextbox(bottom_frame, wrap="word")
        rep_box.grid(row=0, column=2, sticky="nsew", padx=(5, 5), pady=5)

        winners_box.configure(state="normal")
        winners_box.delete("1.0", "end")

        rep_box.configure(state="normal")
        rep_box.delete("1.0", "end")

        league_hist = getattr(sim, "LEAGUE_HISTORY", [])
        cup_hist = getattr(sim, "CUP_HISTORY", [])

        winners = []
        for season_index, season_res in enumerate(league_hist, start=1):
            res = season_res.get(comp_id)
            if not res:
                continue
            table = res.get("table", [])
            if not table:
                continue
            winners.append((season_index, table[0].get("teamName", "Unknown")))

        for season_index, season_res in enumerate(cup_hist, start=1):
            res = season_res.get(comp_id)
            if not res:
                continue
            winner_name = res.get("winner")
            if winner_name:
                winners.append((season_index, winner_name))

        winners.sort(key=lambda x: x[0])
        if winners:
            for s, name in winners:
                winners_box.insert("end", f"Season {s}: {name}\n")
        else:
            winners_box.insert("end", "No winners recorded yet.\n")
        winners_box.configure(state="disabled")

        if league_hist:
            last_season = league_hist[-1]
            res = last_season.get(comp_id)
            if res:
                table = res.get("table", [])
                for pos, row in enumerate(table, start=1):
                    comp_table.insert(
                        "",
                        "end",
                        values=(
                            pos,
                            row.get("teamName", ""),
                            row.get("played", 0),
                            row.get("wins", 0),
                            row.get("draws", 0),
                            row.get("losses", 0),
                            row.get("gf", 0),
                            row.get("ga", 0),
                            row.get("gd", 0),
                            row.get("points", 0),
                        ),
                    )

        rep_box.insert("end", "Teams by reputation:\n")
        teams = sim.COMP_TEAMS.get(comp_id, [])
        teams_sorted_rep = sorted(teams, key=lambda t: t.get("reputationFactor", 0), reverse=True)
        for t in teams_sorted_rep:
            rep_stars = self._to_stars(t.get("reputationFactor", 0))
            fin_stars = self._to_stars(t.get("financial", 0))
            rep_box.insert(
                "end",
                f"  {t.get('teamName','')}: rep {rep_stars}, fin {fin_stars}\n"
            )

        rep_box.insert("end", "\nTeams by titles in this competition:\n")
        title_counts = []
        for tid, hist in sim.TEAM_HISTORY.items():
            base = sim.TEAM_ID_MAP.get(tid, {})
            trophies = base.get("trophies", {})
            base_count = 0
            if isinstance(trophies, dict):
                base_count = int(trophies.get(str(comp_id), 0))
            extra = 0
            for r in hist.get("records", []):
                if r.get("compId") != comp_id:
                    continue
                if r.get("type") == "league" and r.get("position") == 1:
                    extra += 1
                elif r.get("type") == "cup" and r.get("winner"):
                    extra += 1
            total = base_count + extra
            if total > 0:
                title_counts.append((hist.get("name", f"Team {tid}"), total))
        title_counts.sort(key=lambda x: x[1], reverse=True)
        if title_counts:
            for name, cnt in title_counts:
                rep_box.insert("end", f"  {name}: {cnt}\n")
        else:
            rep_box.insert("end", "  No titles recorded yet.\n")

        rep_box.configure(state="disabled")
        self.notebook.select(self.comp_detail_tab)

    # ---------- Team view ----------

    def _open_team_tab(self, team_id):
        for w in self.team_tab.winfo_children():
            w.destroy()

        info = sim.TEAM_HISTORY.get(team_id)
        team_obj = sim.TEAM_ID_MAP.get(team_id)
        if info is None or team_obj is None:
            self._build_empty_team_tab()
            self.notebook.select(self.team_tab)
            return

        self.current_team_id = team_id
        self._trophy_images = []

        self.team_tab.rowconfigure(2, weight=1)
        self.team_tab.columnconfigure(0, weight=1)

        top_frame = ctk.CTkFrame(self.team_tab, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        top_frame.grid_columnconfigure(1, weight=1)

        self._load_logo_image(team_id, size=(64, 64))
        if self._team_logo_image is not None:
            logo_label = ctk.CTkLabel(top_frame, image=self._team_logo_image, text="")
            logo_label.grid(row=0, column=0, rowspan=2, padx=(0, 10), pady=0, sticky="w")

        name_label = ctk.CTkLabel(
            top_frame,
            text=info.get("name", ""),
            font=ctk.CTkFont(size=20, weight="bold")
        )
        name_label.grid(row=0, column=1, sticky="w", padx=5, pady=(0, 2))

        stats_frame = ctk.CTkFrame(self.team_tab)
        stats_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        for i in range(4):
            stats_frame.grid_columnconfigure(i, weight=1)

        rep_stars = self._to_stars(team_obj.get("reputationFactor", 0))
        fin_stars = self._to_stars(team_obj.get("financial", 0))

        ctk.CTkLabel(
            stats_frame,
            text=f"Reputation: {rep_stars}"
        ).grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ctk.CTkLabel(
            stats_frame,
            text=f"Finance: {fin_stars}"
        ).grid(row=0, column=1, padx=5, pady=2, sticky="w")
        ctk.CTkLabel(
            stats_frame,
            text=f"Dev rate: {team_obj.get('devRate', 0)}"
        ).grid(row=0, column=2, padx=5, pady=2, sticky="w")

        ctk.CTkLabel(
            stats_frame,
            text=f"Attack: {team_obj.get('attack', 0)}"
        ).grid(row=1, column=0, padx=5, pady=2, sticky="w")
        ctk.CTkLabel(
            stats_frame,
            text=f"Midfield: {team_obj.get('midfield', 0)}"
        ).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        ctk.CTkLabel(
            stats_frame,
            text=f"Defense: {team_obj.get('defense', 0)}"
        ).grid(row=1, column=2, padx=5, pady=2, sticky="w")
        ctk.CTkLabel(
            stats_frame,
            text=f"GK: {team_obj.get('goalkeeping', 0)}"
        ).grid(row=1, column=3, padx=5, pady=2, sticky="w")

        lower_frame = ctk.CTkFrame(self.team_tab)
        lower_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 10))
        lower_frame.rowconfigure(0, weight=1)
        lower_frame.rowconfigure(1, weight=2)
        lower_frame.columnconfigure(0, weight=1)
        lower_frame.columnconfigure(1, weight=1)

        trophies_frame = ctk.CTkFrame(lower_frame)
        trophies_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=(5, 5))
        trophies_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(trophies_frame, text="Trophies").grid(
            row=0, column=0, sticky="w", padx=5, pady=(3, 2)
        )

        trophies = self._compute_trophies(team_id, team_obj, info)
        if trophies:
            image_trophies = []
            text_trophies = []

            for cid, count in sorted(trophies.items(), key=lambda kv: -kv[1]):
                comp_name = sim.COMP_NAME_LOOKUP.get(cid, f"Comp {cid}")
                icon = self._load_trophy_image(cid, size=(36, 36))
                if icon is not None:
                    image_trophies.append((cid, comp_name, icon, count))
                else:
                    text_trophies.append((comp_name, count))

            if image_trophies:
                for col, (cid, comp_name, icon, count) in enumerate(image_trophies):
                    icon_label = ctk.CTkLabel(trophies_frame, image=icon, text="")
                    icon_label.grid(row=1, column=col, padx=10, pady=(4, 0))
                    SimpleTooltip(icon_label, comp_name)
                    icon_label.bind("<Button-1>", lambda e, cc=cid: self._open_competition_tab(cc))
                    amt_label = ctk.CTkLabel(
                        trophies_frame,
                        text=str(count),
                        font=ctk.CTkFont(size=14, weight="bold")
                    )
                    amt_label.grid(row=2, column=col, padx=10, pady=(0, 6))

            if text_trophies:
                start_row = 3
                for i, (comp_name, count) in enumerate(text_trophies):
                    row_frame = ctk.CTkFrame(trophies_frame, fg_color="transparent")
                    row_frame.grid(row=start_row + i, column=0, sticky="w", padx=5, pady=2)
                    ctk.CTkLabel(row_frame, text=f"{comp_name}: {count}").pack(side="left")
        else:
            ctk.CTkLabel(
                trophies_frame,
                text="No trophies recorded yet."
            ).grid(row=1, column=0, sticky="w", padx=5, pady=(0, 4))

        records_frame = ctk.CTkFrame(lower_frame)
        records_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=0)
        records_frame.rowconfigure(1, weight=1)
        records_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(records_frame, text="Season records").grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0)
        )
        records_box = ctk.CTkTextbox(records_frame, wrap="word")
        records_box.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        records_box.configure(state="normal")
        records = info.get("records", [])
        records_sorted = sorted(records, key=lambda r: (r.get("season", 0), r.get("type", "")))
        last_season = None
        for r in records_sorted:
            s = r.get("season", 0)
            if s != last_season:
                records_box.insert("end", f"\nSeason {s}\n")
                last_season = s
            if r.get("type") == "league":
                records_box.insert(
                    "end",
                    f"  {r.get('compName')}: Position: {r.get('position')} "
                    f"Pts {r.get('points')} GD: {r.get('gd')}\n"
                )
            elif r.get("type") == "cup":
                desc = f"  {r.get('compName')}: Reached {r.get('best_round')}"
                if r.get("winner"):
                    desc += " (Winner)"
                records_box.insert("end", desc + "\n")
        records_box.configure(state="disabled")

        graph_frame = ctk.CTkFrame(lower_frame)
        graph_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=0)
        graph_frame.rowconfigure(1, weight=1)
        graph_frame.rowconfigure(3, weight=1)
        graph_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(graph_frame, text="Ratings over seasons").grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0)
        )

        canvas_ratings = tk.Canvas(graph_frame, bg="#111111", highlightthickness=0)
        canvas_ratings.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        ratings = info.get("ratings", [])
        if ratings:
            width = 360
            height = 200
            canvas_ratings.configure(width=width, height=height)
            seasons_r = [r["season"] for r in ratings]
            seasons_r_sorted = sorted(seasons_r)
            min_s = min(seasons_r_sorted)
            max_s = max(seasons_r_sorted)
            if max_s == min_s:
                max_s += 1
            attrs = ["attack", "midfield", "defense", "goalkeeping"]
            colors = {
                "attack": "red",
                "midfield": "yellow",
                "defense": "cyan",
                "goalkeeping": "magenta"
            }
            min_val = 50
            max_val = 100
            margin = 30

            canvas_ratings.create_line(
                margin, height - margin, width - margin, height - margin, fill="#555555"
            )
            canvas_ratings.create_line(
                margin, margin, margin, height - margin, fill="#555555"
            )

            for y_val in range(min_val, max_val + 1, 10):
                y = height - margin - (y_val - min_val) / (max_val - min_val) * (height - 2 * margin)
                canvas_ratings.create_line(margin, y, width - margin, y, fill="#222222")
                canvas_ratings.create_text(
                    margin - 10, y, text=str(y_val), fill="#bbbbbb", anchor="e", font=("Arial", 8)
                )

            seasons_unique = seasons_r_sorted
            n_seasons = len(seasons_unique)
            for i, s in enumerate(seasons_unique):
                x = margin + i / max(1, n_seasons - 1) * (width - 2 * margin)
                canvas_ratings.create_text(
                    x, height - margin + 10, text=str(s), fill="#bbbbbb", anchor="n", font=("Arial", 8)
                )

            for attr in attrs:
                points = []
                for i, s in enumerate(seasons_unique):
                    for r in ratings:
                        if r["season"] == s:
                            v = r.get(attr, 0)
                            break
                    else:
                        v = None
                    if v is None:
                        continue
                    x = margin + i / max(1, n_seasons - 1) * (width - 2 * margin)
                    v_clamped = max(min_val, min(max_val, v))
                    y = height - margin - (v_clamped - min_val) / (max_val - min_val) * (height - 2 * margin)
                    points.append((x, y))
                if len(points) >= 2:
                    flat = []
                    for x, y in points:
                        flat.extend([x, y])
                    canvas_ratings.create_line(flat, fill=colors.get(attr, "white"), width=2)
                elif len(points) == 1:
                    x, y = points[0]
                    canvas_ratings.create_oval(x - 2, y - 2, x + 2, y + 2, fill=colors.get(attr, "white"))

            legend_y = margin
            for attr in attrs:
                col = colors.get(attr, "white")
                canvas_ratings.create_line(
                    width - margin - 50, legend_y, width - margin - 30, legend_y, fill=col, width=2
                )
                canvas_ratings.create_text(
                    width - margin - 25, legend_y, text=attr[:3].upper(), fill="#ffffff", anchor="w",
                    font=("Arial", 8)
                )
                legend_y += 12

        ctk.CTkLabel(graph_frame, text="League positions over seasons").grid(
            row=2, column=0, sticky="w", padx=5, pady=(5, 0)
        )

        canvas_pos = tk.Canvas(graph_frame, bg="#111111", highlightthickness=0)
        canvas_pos.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)

        positions_by_season = self._league_positions_by_season(info)
        if positions_by_season:
            width_p = 360
            height_p = 200
            canvas_pos.configure(width=width_p, height=height_p)

            seasons_p = sorted(positions_by_season.keys())
            pos_vals = [positions_by_season[s]["position"] for s in seasons_p]
            min_pos = 1
            max_pos = max(pos_vals)
            if max_pos == min_pos:
                max_pos += 1
            margin_p = 30

            canvas_pos.create_line(
                margin_p, margin_p, margin_p, height_p - margin_p, fill="#555555"
            )
            canvas_pos.create_line(
                margin_p, height_p - margin_p, width_p - margin_p, height_p - margin_p, fill="#555555"
            )

            for pos in range(min_pos, max_pos + 1):
                frac = (pos - min_pos) / (max_pos - min_pos)
                y = margin_p + frac * (height_p - 2 * margin_p)
                canvas_pos.create_line(margin_p, y, width_p - margin_p, y, fill="#222222")
                canvas_pos.create_text(
                    margin_p - 10, y, text=str(pos), fill="#bbbbbb", anchor="e", font=("Arial", 8)
                )

            n_seasons = len(seasons_p)
            points = []
            for i, s in enumerate(seasons_p):
                pos = positions_by_season[s]["position"]
                x = margin_p + i / max(1, n_seasons - 1) * (width_p - 2 * margin_p)
                frac = (pos - min_pos) / (max_pos - min_pos)
                y = margin_p + frac * (height_p - 2 * margin_p)
                points.append((x, y))
                canvas_pos.create_text(
                    x, height_p - margin_p + 10, text=str(s), fill="#bbbbbb", anchor="n", font=("Arial", 8)
                )

            if len(points) >= 2:
                flat = []
                for x, y in points:
                    flat.extend([x, y])
                canvas_pos.create_line(flat, fill="white", width=2)

            for (x, y), s in zip(points, seasons_p):
                canvas_pos.create_oval(x - 3, y - 3, x + 3, y + 3, outline="yellow", fill="yellow")

        self.notebook.select(self.team_tab)

    # ---------- Home interactions ----------

    def _on_select_competition_from_home(self, comp_id):
        name = sim.COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
        values = list(self.comp_select.cget("values"))
        if name in values:
            self.comp_select.set(name)

        self.current_competition_id = comp_id

        self._update_table_for_competition()
        self.notebook.select(self.league_tab)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()

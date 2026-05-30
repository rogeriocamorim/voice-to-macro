"""
gui/game_info_tab.py — Game Info & EDSM/Spansh Q&A tab.

Split view:
- Top: Live game state panel (system, station, ship, fuel, cargo, credits, flags)
- Bottom: Question/Answer panel to query EDSM/Spansh APIs (stations, trade, system info)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def _ts() -> str:
    return datetime.now().strftime("%I:%M:%S %p")


# ------------------------------------------------------------------
# Background worker for API queries (avoids freezing the GUI)
# ------------------------------------------------------------------

class _QueryWorker(QThread):
    """Run an EDSM/Spansh query in the background."""

    result = pyqtSignal(str)  # HTML-formatted result
    error = pyqtSignal(str)

    def __init__(
        self,
        query_type: str,
        query_text: str,
        edsm: Any,
        spansh: Any,
        game_state: Any,
        config: dict,
        parent=None,
    ):
        super().__init__(parent)
        self._query_type = query_type
        self._query_text = query_text.strip()
        self._edsm = edsm
        self._spansh = spansh
        self._game_state = game_state
        self._config = config

    def run(self) -> None:
        try:
            if self._query_type == "System Info":
                self._query_system_info()
            elif self._query_type == "Stations":
                self._query_stations()
            elif self._query_type == "Traffic & Danger":
                self._query_traffic()
            elif self._query_type == "Bodies & Exploration":
                self._query_bodies()
            elif self._query_type == "Trade Route":
                self._query_trade_route()
            elif self._query_type == "Find Commodity":
                self._query_find_commodity()
            elif self._query_type == "Commander Info":
                self._query_commander()
            else:
                self.error.emit(f"Unknown query type: {self._query_type}")
        except Exception as e:
            self.error.emit(f"Error: {e}")

    # -- Query implementations --

    def _system_name(self) -> str:
        """Resolve target system: use query text if provided, else current system."""
        if self._query_text:
            return self._query_text
        if self._game_state:
            current = self._game_state.get_current_system()
            if current:
                return current
        return ""

    def _query_system_info(self) -> None:
        system = self._system_name()
        if not system:
            self.error.emit("Enter a system name or fly to a system first.")
            return
        if not self._edsm:
            self.error.emit("EDSM client not available. Is Elite integration active?")
            return

        data = self._edsm.get_system(system)
        if not data:
            self.error.emit(f"No EDSM data found for system '{system}'.")
            return

        lines = [f"<b>System: {data.get('name', system)}</b>"]

        coords = data.get("coords", {})
        if coords:
            lines.append(f"Coordinates: {coords.get('x', '?')}, {coords.get('y', '?')}, {coords.get('z', '?')}")

        info = data.get("information", {})
        if info:
            if info.get("allegiance"):
                lines.append(f"Allegiance: {info['allegiance']}")
            if info.get("government"):
                lines.append(f"Government: {info['government']}")
            if info.get("economy"):
                lines.append(f"Economy: {info['economy']}")
            if info.get("secondEconomy"):
                lines.append(f"Second Economy: {info['secondEconomy']}")
            if info.get("security"):
                lines.append(f"Security: {info['security']}")
            if info.get("population") is not None:
                lines.append(f"Population: {info['population']:,}")
            if info.get("faction"):
                lines.append(f"Controlling Faction: {info['faction']}")

        star = data.get("primaryStar", {})
        if star:
            lines.append(f"Primary Star: {star.get('type', '?')} ({star.get('name', '?')})")
            if star.get("isScoopable"):
                lines.append("  Scoopable: Yes")

        self.result.emit("<br>".join(lines))

    def _query_stations(self) -> None:
        system = self._system_name()
        if not system:
            self.error.emit("Enter a system name or fly to a system first.")
            return
        if not self._edsm:
            self.error.emit("EDSM client not available.")
            return

        data = self._edsm.get_stations(system)
        if not data or not data.get("stations"):
            self.error.emit(f"No stations found in '{system}'.")
            return

        lines = [f"<b>Stations in {system}</b>"]
        for st in data["stations"]:
            name = st.get("name", "?")
            st_type = st.get("type", "?")
            dist = st.get("distanceToArrival")
            dist_str = f"{dist:,.0f} ls" if dist else "?"
            market = "Market" if st.get("haveMarket") else "No market"
            pad = ""
            if st.get("maxLandingPadSize"):
                pad = f" | Pad: {st['maxLandingPadSize']}"
            lines.append(f"  {name} ({st_type}) - {dist_str} | {market}{pad}")

        self.result.emit("<br>".join(lines))

    def _query_traffic(self) -> None:
        system = self._system_name()
        if not system:
            self.error.emit("Enter a system name or fly to a system first.")
            return
        if not self._edsm:
            self.error.emit("EDSM client not available.")
            return

        lines = [f"<b>Traffic & Danger: {system}</b>"]

        traffic = self._edsm.get_traffic(system)
        if traffic and traffic.get("traffic"):
            t = traffic["traffic"]
            lines.append(f"Traffic - Total: {t.get('total', 0):,} | Week: {t.get('week', 0):,} | Day: {t.get('day', 0):,}")

        deaths = self._edsm.get_deaths(system)
        if deaths and deaths.get("deaths"):
            d = deaths["deaths"]
            lines.append(f"Deaths - Total: {d.get('total', 0):,} | Week: {d.get('week', 0):,} | Day: {d.get('day', 0):,}")
            if d.get("total", 0) > 100:
                lines.append('<span style="color: #f38ba8">WARNING: High death count — dangerous system!</span>')

        if len(lines) == 1:
            self.error.emit(f"No traffic/death data for '{system}'.")
            return

        self.result.emit("<br>".join(lines))

    def _query_bodies(self) -> None:
        system = self._system_name()
        if not system:
            self.error.emit("Enter a system name or fly to a system first.")
            return
        if not self._edsm:
            self.error.emit("EDSM client not available.")
            return

        lines = [f"<b>Bodies in {system}</b>"]

        # Estimated value
        value = self._edsm.get_estimated_value(system)
        if value:
            ev = value.get("estimatedValue", 0)
            evm = value.get("estimatedValueMapped", 0)
            lines.append(f"Estimated scan value: {ev:,} cr (mapped: {evm:,} cr)")

            valuable = value.get("valuableBodies", [])
            if valuable:
                lines.append("<b>Valuable bodies:</b>")
                for b in valuable[:10]:
                    lines.append(f"  {b.get('bodyName', '?')} — {b.get('valueMax', 0):,} cr")

        # Bodies list
        bodies = self._edsm.get_bodies(system)
        if bodies and bodies.get("bodies"):
            lines.append(f"<b>Total bodies: {len(bodies['bodies'])}</b>")
            for b in bodies["bodies"][:15]:
                name = b.get("name", "?")
                btype = b.get("subType") or b.get("type", "?")
                dist = b.get("distanceToArrival")
                dist_str = f"{dist:,.0f} ls" if dist else "?"
                terraform = ""
                if b.get("terraformingState") and b["terraformingState"] != "Not terraformable":
                    terraform = f' [{b["terraformingState"]}]'
                lines.append(f"  {name} ({btype}) - {dist_str}{terraform}")

        if len(lines) == 1:
            self.error.emit(f"No body data for '{system}'.")
            return

        self.result.emit("<br>".join(lines))

    def _query_trade_route(self) -> None:
        if not self._spansh:
            self.error.emit("Spansh client not available. Is Elite integration active?")
            return

        system = None
        station = None

        if self._game_state:
            system = self._game_state.get_current_system()
            station = self._game_state.get_current_station()

        # Allow override from query text: "System / Station"
        if self._query_text:
            parts = [p.strip() for p in self._query_text.split("/")]
            if len(parts) >= 2:
                system, station = parts[0], parts[1]
            elif len(parts) == 1 and parts[0]:
                system = parts[0]

        if not system or not station:
            self.error.emit(
                "Dock at a station first, or enter 'System / Station' in the query box."
            )
            return

        self.result.emit(f"Calculating trade route from {station} ({system})...<br>This may take up to 60 seconds.")

        config = self._config
        route = self._spansh.trade_route(
            system=system,
            station=station,
            max_hops=config.get("trade_max_hops", 5),
            max_hop_distance=config.get("trade_max_hop_distance", 30.0),
            starting_capital=config.get("trade_starting_capital", 10_000_000),
            max_cargo=config.get("trade_max_cargo", 200),
            requires_large_pad=config.get("trade_requires_large_pad", True),
        )

        if not route:
            self.error.emit("No trade route found. Try different parameters.")
            return

        lines = [f"<b>Trade Route from {station} ({system})</b>"]
        total_profit = 0
        for i, leg in enumerate(route):
            src = leg.get("source_station", leg.get("source", {}).get("station", "?"))
            src_sys = leg.get("source_system", leg.get("source", {}).get("system", "?"))
            dst = leg.get("destination_station", leg.get("destination", {}).get("station", "?"))
            dst_sys = leg.get("destination_system", leg.get("destination", {}).get("system", "?"))

            profit = leg.get("profit", leg.get("total_profit", 0))
            total_profit += profit

            lines.append(f"<b>Hop {i + 1}:</b> {src_sys} / {src} -> {dst_sys} / {dst}")

            commodities = leg.get("commodities", [])
            for c in commodities:
                cname = c.get("name", "?")
                qty = c.get("max_supply", c.get("quantity", "?"))
                cprofit = c.get("profit", 0)
                lines.append(f"  Buy {cname} x{qty} (profit: {cprofit:,} cr/t)")

            if profit:
                lines.append(f"  Leg profit: {profit:,} cr")

        lines.append(f"<br><b>Total estimated profit: {total_profit:,} cr</b>")
        self.result.emit("<br>".join(lines))

    def _query_find_commodity(self) -> None:
        commodity = self._query_text
        if not commodity:
            self.error.emit("Enter a commodity name (e.g. 'Gold', 'Void Opals').")
            return
        if not self._spansh:
            self.error.emit("Spansh client not available.")
            return

        ref_system = None
        if self._game_state:
            ref_system = self._game_state.get_current_system()
        if not ref_system:
            ref_system = "Sol"

        self.result.emit(f"Searching for '{commodity}' near {ref_system}...")

        results = self._spansh.search_stations(
            reference_system=ref_system,
            filters={
                "market": [{"name": commodity}],
                "has_large_pad": {"value": True},
            },
            size=10,
        )

        if not results:
            self.error.emit(f"No stations found selling '{commodity}' nearby.")
            return

        lines = [f"<b>Stations selling '{commodity}' near {ref_system}</b>"]
        for st in results:
            name = st.get("name", "?")
            system = st.get("system_name", st.get("system", {}).get("name", "?"))
            dist = st.get("distance", st.get("distance_to_ref", "?"))
            dist_str = f"{dist:.1f} ly" if isinstance(dist, (int, float)) else str(dist)
            lines.append(f"  {name} ({system}) - {dist_str}")

        self.result.emit("<br>".join(lines))

    def _query_commander(self) -> None:
        if not self._edsm:
            self.error.emit("EDSM client not available.")
            return

        cmdr = self._config.get("edsm_commander_name")
        api_key = self._config.get("edsm_api_key")
        if not cmdr or not api_key:
            self.error.emit(
                "EDSM commander name and API key required.\n"
                "Set edsm_commander_name and edsm_api_key in config.yaml."
            )
            return

        lines = [f"<b>Commander: {cmdr}</b>"]

        # Position
        pos = self._edsm.get_position(cmdr, api_key)
        if pos:
            lines.append(f"Last known system: {pos.get('system', '?')}")
            if pos.get("firstDiscover"):
                lines.append("  (First discoverer!)")

        # Ranks
        ranks = self._edsm.get_ranks(cmdr, api_key)
        if ranks:
            verbose = ranks.get("ranksVerbose", {})
            progress = ranks.get("progress", {})
            for rank_name, rank_val in verbose.items():
                prog = progress.get(rank_name, 0)
                lines.append(f"  {rank_name}: {rank_val} ({prog}%)")

        # Credits
        credits_data = self._edsm.get_credits(cmdr, api_key)
        if credits_data and credits_data.get("credits"):
            latest = credits_data["credits"][0]
            bal = latest.get("balance", 0)
            lines.append(f"Credits: {bal:,} cr")

        if len(lines) == 1:
            self.error.emit("Could not retrieve commander data. Check your EDSM API key.")
            return

        self.result.emit("<br>".join(lines))


# ------------------------------------------------------------------
# The tab widget
# ------------------------------------------------------------------

class GameInfoTab(QWidget):
    """Game state viewer + EDSM/Spansh Q&A panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine: Any = None
        self._game_state: Any = None
        self._edsm: Any = None
        self._spansh: Any = None
        self._config: dict = {}
        self._worker: _QueryWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ---- Top: Live game state ----
        state_widget = QWidget()
        state_layout = QVBoxLayout(state_widget)
        state_layout.setContentsMargins(4, 4, 4, 4)

        state_label = QLabel("Game State")
        state_label.setObjectName("sectionLabel")
        state_layout.addWidget(state_label)

        # State grid
        state_grid = QWidget()
        grid = QHBoxLayout(state_grid)
        grid.setContentsMargins(0, 0, 0, 0)

        # Left column
        left = QVBoxLayout()
        self.lbl_system = self._make_field("System:", "---")
        self.lbl_station = self._make_field("Station:", "---")
        self.lbl_commander = self._make_field("Commander:", "---")
        self.lbl_ship = self._make_field("Ship:", "---")
        left.addLayout(self.lbl_system)
        left.addLayout(self.lbl_station)
        left.addLayout(self.lbl_commander)
        left.addLayout(self.lbl_ship)
        left.addStretch()

        # Right column
        right = QVBoxLayout()
        self.lbl_fuel = self._make_field("Fuel:", "---")
        self.lbl_cargo = self._make_field("Cargo:", "---")
        self.lbl_credits = self._make_field("Credits:", "---")
        self.lbl_destination = self._make_field("Destination:", "---")
        right.addLayout(self.lbl_fuel)
        right.addLayout(self.lbl_cargo)
        right.addLayout(self.lbl_credits)
        right.addLayout(self.lbl_destination)
        right.addStretch()

        grid.addLayout(left)
        grid.addLayout(right)
        state_layout.addWidget(state_grid)

        # Flags row
        self.lbl_flags = QLabel("")
        self.lbl_flags.setWordWrap(True)
        self.lbl_flags.setStyleSheet("color: #6c7086; font-size: 11px;")
        state_layout.addWidget(self.lbl_flags)

        splitter.addWidget(state_widget)

        # ---- Bottom: Q&A panel ----
        qa_widget = QWidget()
        qa_layout = QVBoxLayout(qa_widget)
        qa_layout.setContentsMargins(4, 4, 4, 4)

        qa_label = QLabel("Query EDSM / Spansh")
        qa_label.setObjectName("sectionLabel")
        qa_layout.addWidget(qa_label)

        # Query controls
        controls = QHBoxLayout()

        self.query_type = QComboBox()
        self.query_type.addItems([
            "System Info",
            "Stations",
            "Traffic & Danger",
            "Bodies & Exploration",
            "Trade Route",
            "Find Commodity",
            "Commander Info",
        ])
        self.query_type.setMinimumWidth(160)
        controls.addWidget(self.query_type)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("System name, commodity, or leave blank for current system...")
        self.query_input.returnPressed.connect(self._run_query)
        controls.addWidget(self.query_input)

        self.query_btn = QPushButton("Search")
        self.query_btn.setMinimumWidth(80)
        self.query_btn.clicked.connect(self._run_query)
        controls.addWidget(self.query_btn)

        qa_layout.addLayout(controls)

        # Results display
        self.results_view = QTextEdit()
        self.results_view.setReadOnly(True)
        self.results_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.results_view.setPlaceholderText(
            "Select a query type and click Search.\n"
            "Leave the text field blank to use your current system.\n\n"
            "Examples:\n"
            "  System Info + 'Sol'  ->  Info about the Sol system\n"
            "  Stations + ''       ->  Stations in your current system\n"
            "  Find Commodity + 'Gold'  ->  Nearby stations selling Gold\n"
            "  Trade Route + ''    ->  Trade route from your current station\n"
            "  Trade Route + 'System / Station'  ->  Route from specific station"
        )
        qa_layout.addWidget(self.results_view)

        splitter.addWidget(qa_widget)

        # Give more space to the Q&A panel
        splitter.setSizes([200, 400])

        layout.addWidget(splitter)

    def _make_field(self, label_text: str, default: str) -> QHBoxLayout:
        """Create a label: value pair and return the layout. Stores the value label."""
        row = QHBoxLayout()
        key = QLabel(label_text)
        key.setStyleSheet("color: #89b4fa; font-weight: bold; min-width: 100px;")
        key.setFixedWidth(110)
        val = QLabel(default)
        val.setStyleSheet("color: #cdd6f4;")
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(key)
        row.addWidget(val)
        row.addStretch()

        # Store value label on the layout object for later updates
        row._value_label = val  # type: ignore[attr-defined]
        return row

    @staticmethod
    def _set_field(field_layout: QHBoxLayout, text: str) -> None:
        """Update the value label in a field layout."""
        label = getattr(field_layout, "_value_label", None)
        if label:
            label.setText(text)

    # ------------------------------------------------------------------
    # Public API (called from MainWindow)
    # ------------------------------------------------------------------

    def set_engine(self, engine: Any, config: dict) -> None:
        """
        Store a reference to the VoiceEngine so we can poll its game
        state / EDSM / Spansh as they become available (they are set
        asynchronously inside the engine thread).
        """
        self._engine = engine
        self._config = config

    def _sync_from_engine(self) -> None:
        """Pull the latest references from the engine (they may appear later)."""
        engine = getattr(self, "_engine", None)
        if not engine:
            return
        if not self._game_state and getattr(engine, "_game_state", None):
            self._game_state = engine._game_state
        if not self._edsm and getattr(engine, "_edsm", None):
            self._edsm = engine._edsm
        if not self._spansh and getattr(engine, "_spansh", None):
            self._spansh = engine._spansh

    def update_game_state(self) -> None:
        """Refresh the game state display from the current GameState object."""
        self._sync_from_engine()

        gs = self._game_state
        if not gs:
            return

        self._set_field(self.lbl_system, gs.get_current_system() or "---")
        self._set_field(self.lbl_station, gs.get_current_station() or "Not docked")
        self._set_field(self.lbl_commander, gs.get_commander() or "---")

        # Ship
        ship_parts = []
        ship_type = gs.get_ship_type()
        ship_name = gs.get_ship_name()
        if ship_name:
            ship_parts.append(ship_name)
        if ship_type:
            ship_parts.append(f"({ship_type})")
        self._set_field(self.lbl_ship, " ".join(ship_parts) if ship_parts else "---")

        # Fuel
        fuel_level, fuel_cap = gs.get_fuel()
        if fuel_level is not None:
            if fuel_cap:
                fuel_str = f"{fuel_level:.1f} / {fuel_cap:.1f} t"
            else:
                fuel_str = f"{fuel_level:.1f} t"
            if gs.is_low_fuel():
                fuel_str += "  [LOW FUEL]"
            self._set_field(self.lbl_fuel, fuel_str)

        # Cargo
        cargo = gs.get_cargo()
        self._set_field(self.lbl_cargo, f"{cargo:.0f} t")

        # Credits
        balance = gs.get_balance()
        if balance is not None:
            self._set_field(self.lbl_credits, f"{balance:,} cr")

        # Destination
        dest = gs.get_destination()
        if dest and dest.get("Name"):
            self._set_field(self.lbl_destination, dest["Name"])
        else:
            self._set_field(self.lbl_destination, "---")

        # Flags
        flags = []
        if gs.is_docked():
            flags.append("Docked")
        if gs.is_landed():
            flags.append("Landed")
        if gs.is_supercruise():
            flags.append("Supercruise")
        if gs.is_in_hyperspace():
            flags.append("Hyperspace")
        if gs.is_hardpoints_deployed():
            flags.append("Hardpoints")
        if gs.is_cargo_scoop_deployed():
            flags.append("Cargo Scoop")
        if gs.is_landing_gear_down():
            flags.append("Gear Down")
        if gs.is_shields_up():
            flags.append("Shields Up")
        if gs.is_lights_on():
            flags.append("Lights")
        if gs.is_silent_running():
            flags.append("Silent Running")
        if gs.is_fsd_charging():
            flags.append("FSD Charging")
        if gs.is_in_danger():
            flags.append("[DANGER]")
        if gs.is_being_interdicted():
            flags.append("[INTERDICTED]")
        if gs.is_night_vision():
            flags.append("Night Vision")

        pips = gs.get_pips()
        pips_str = f"SYS:{pips[0]} ENG:{pips[1]} WEP:{pips[2]}" if pips else ""

        flag_text = " | ".join(flags) if flags else "No flags"
        if pips_str:
            flag_text += f"    Pips: {pips_str}"
        self.lbl_flags.setText(flag_text)

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def _run_query(self) -> None:
        if self._worker and self._worker.isRunning():
            return

        self._sync_from_engine()

        query_type = self.query_type.currentText()
        query_text = self.query_input.text().strip()

        self.results_view.clear()
        self.results_view.append(
            f'<span style="color: #89b4fa">[{_ts()}] Querying {query_type}...</span>'
        )
        self.query_btn.setEnabled(False)
        self.query_btn.setText("...")

        self._worker = _QueryWorker(
            query_type=query_type,
            query_text=query_text,
            edsm=self._edsm,
            spansh=self._spansh,
            game_state=self._game_state,
            config=self._config,
            parent=self,
        )
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_result(self, html: str) -> None:
        self.results_view.append(html)

    def _on_error(self, msg: str) -> None:
        self.results_view.append(f'<span style="color: #f38ba8">{msg}</span>')

    def _on_finished(self) -> None:
        self.query_btn.setEnabled(True)
        self.query_btn.setText("Search")
        self._worker = None

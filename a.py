from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.containers import Center, Middle

class DetailScreen(ModalScreen):
    """A modal screen that displays row details."""
    def __init__(self, row_data: list):
        super().__init__()
        self.row_data = row_data

    def compose(self) -> ComposeResult:
        details = (
            f"[bold cyan]Name:[/]   {self.row_data[0]}\n"
            f"[bold cyan]Label:[/]  {self.row_data[1]}\n"
            f"[bold cyan]Active:[/] {self.row_data[2]}\n"
            f"[bold cyan]GPU:[/]    {self.row_data[3]}"
        )
        with Middle():
            with Center():
                yield Static(details, id="detail_panel")
                yield Static("Press any key to close", id="hint")

    def on_key(self) -> None:
        self.app.pop_screen()

class SampleTableApp(App):
    CSS = """
    DataTable {
        height: 1fr;
        border: round $primary;
        margin: 1;
    }
    #detail_panel {
        width: 40;
        height: 10;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
        content-align: left middle;
    }
    #hint { text-align: center; color: $text-disabled; margin-top: 1; }
    """

    BINDINGS = [
        Binding("e", "show_details", "Show Row Details"),
        Binding("t", "toggle_active", "Toggle Active Cell"),
        Binding("q", "quit", "Quit")
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "cell"
        
        table.add_columns("Name", "Label", "Active", "GPU")
        table.add_rows([
            ["node-01", "Primary", "True", "RTX 4090"],
            ["node-02", "Backup", "False", "N/A"],
            ["node-03", "Compute", "True", "A100"],
        ])

    def action_show_details(self) -> None:
        """Pops up details for the current row, regardless of cell focused."""
        table = self.query_one(DataTable)
        coord = table.cursor_coordinate
        if coord:
            row_key, _ = table.coordinate_to_cell_key(coord)
            row_data = table.get_row(row_key)
            self.push_screen(DetailScreen(row_data))

    def action_toggle_active(self) -> None:
        """Toggles 'Active' only if the cursor is specifically in that column."""
        table = self.query_one(DataTable)
        coord = table.cursor_coordinate
        
        # Column 2 is the "Active" column
        if coord and coord.column == 2:
            current_val = str(table.get_cell_at(coord))
            new_val = "False" if current_val == "True" else "True"
            
            # Update the cell visually
            table.update_cell_at(coord, new_val)
            
            # Note: In a real app, you'd also update your HostManager/Database here.

if __name__ == "__main__":
    SampleTableApp().run()
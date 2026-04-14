from typing import Any, List, Dict, Union

class CellRenderer:
    """
    Handles the rendering of host metrics into human-readable strings
    and determines the appropriate color coding for the GUI.
    """

    @staticmethod
    def render_usage(val: Any) -> Dict[str, str]:
        """Renders usage metrics (GPU/CPU) as '10 20%'."""
        if val == 'N/A' or val is None:
            return {"text": "N/A", "color": "text-slate-400"}
        
        if not isinstance(val, list):
            val = [val]
            
        filtered = [v for v in val if v != 'N/A']
        if not filtered:
            return {"text": "N/A", "color": "text-slate-400"}
            
        text = " ".join(map(str, filtered)) + "%"
        
        # Color logic
        try:
            max_val = max([float(v) for v in filtered if isinstance(v, (int, float))])
            if max_val > 80:
                color = "text-red-400 font-bold"
            elif max_val > 60:
                color = "text-yellow-400"
            else:
                color = "text-green-400"
        except (ValueError, TypeError):
            color = "text-slate-400"
            
        return {"text": text, "color": color}

    @staticmethod
    def render_temp(val: Any) -> Dict[str, str]:
        """Renders temperature metrics as '45 50°C'."""
        if val == 'N/A' or val is None:
            return {"text": "N/A", "color": "text-slate-400"}
            
        if not isinstance(val, list):
            val = [val]
            
        filtered = [v for v in val if v != 'N/A']
        if not filtered:
            return {"text": "N/A", "color": "text-slate-400"}
            
        text = " ".join(map(str, filtered)) + "°C"
        
        # Color logic
        try:
            max_val = max([float(v) for v in filtered if isinstance(v, (int, float))])
            if max_val > 80:
                color = "text-red-400 font-bold"
            elif max_val > 60:
                color = "text-yellow-400"
            else:
                color = "text-green-400"
        except (ValueError, TypeError):
            color = "text-slate-400"
            
        return {"text": text, "color": color}

    @staticmethod
    def render_mem(val: Any) -> Dict[str, str]:
        """Renders memory metrics as '10% 20% (2*80GB)'."""
        if val == 'N/A' or val is None:
            return {"text": "N/A", "color": "text-slate-400"}
            
        if not isinstance(val, list):
            val = [val]
            
        percs = []
        totals = []
        
        for item in val:
            if isinstance(item, list) and len(item) >= 2:
                if item[0] != 'N/A': percs.append(str(item[0]))
                if item[1] != 'N/A': totals.append(item[1])
            elif item != 'N/A':
                percs.append(str(item))
                
        if not percs and not totals:
            return {"text": "N/A", "color": "text-slate-400"}
            
        perc_str = " ".join(percs) + "%" if percs else ""
        total_str = ""
        
        if totals:
            unique_totals = list(set(totals))
            if len(unique_totals) == 1:
                size = unique_totals[0]
                total_str = f"{len(totals)}*{size}GB" if len(totals) > 1 else f"{size}GB"
            else:
                total_str = ", ".join(map(str, unique_totals)) + " GB"
                
        text = f"{perc_str} ({total_str})" if total_str else perc_str
        
        # Memory color is usually based on the first percentage
        color = "text-slate-400"
        if percs:
            try:
                first_perc = float(percs[0].replace('%', ''))
                if first_perc > 80: color = "text-red-400 font-bold"
                elif first_perc > 60: color = "text-yellow-400"
                else: color = "text-green-400"
            except (ValueError, TypeError):
                pass
                
        return {"text": text, "color": color}

    @classmethod
    def render_cell(cls, column_name: str, value: Any) -> Dict[str, str]:
        """
        Dispatcher that selects the specialized renderer based on column name.
        """
        renderers = {
            "gpu_usage": cls.render_usage,
            "cpu_usage": cls.render_usage,
            "gpu_temp": cls.render_temp,
            "cpu_temp": cls.render_temp,
            "mem_usage": cls.render_mem,
        }
        
        renderer = renderers.get(column_name)
        if renderer:
            return renderer(value)
            
        return {"text": str(value), "color": "text-slate-400"}
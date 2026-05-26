#!/usr/bin/env python3
"""
DrugAgent-Local - Menú CLI Interactivo Premium
Permite configurar y lanzar misiones de descubrimiento de fármacos dirigidas
por indicación terapéutica y modo de optimización.
"""
import os
import sys
import yaml
import subprocess
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.live import Live

console = Console()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_banner():
    banner = """
 ██████╗ ██████╗ ██╗   ██╗ ██████╗  █████╗  ██████╗ ███████╗███╗   ██╗████████╗
 ██╔══██╗██╔══██╗██║   ██║██╔════╝ ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
 ██║  ██║██████╔╝██║   ██║██║  ███╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
 ██║  ██║██╔══██╗██║   ██║██║   ██║██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
 ██████╔╝██║  ██║╚██████╔╝╚██████╔╝██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
 ╚══════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
                     🧪 Plataforma de Misiones Terapéuticas v2.0 🧪
    """
    console.print(Panel(Text(banner, style="cyan bold"), border_style="blue", title="[bold white]LABORATORIO VIRTUAL[/bold white]"))

def load_catalog():
    catalog_path = "catalog/therapeutic_areas.yaml"
    if not os.path.exists(catalog_path):
        console.print(f"[bold red]❌ Error: No se encontró el catálogo en '{catalog_path}'[/bold red]")
        sys.exit(1)
    with open(catalog_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_agent_workflow():
    clear_screen()
    show_banner()
    
    catalog = load_catalog()
    
    # 1. Selección de Área Terapéutica
    console.print("\n[bold green]📊 PASO 1: Seleccione la Misión Terapéutica[/bold green]")
    choices = []
    keys_map = {}
    for key, data in catalog.items():
        choice_str = f"{data['display_name']} ({data['pdb_id']})"
        choices.append(choice_str)
        keys_map[choice_str] = (key, data)
        
    selected_choice = questionary.select(
        "Diana farmacológica a investigar:",
        choices=choices
    ).ask()
    
    if not selected_choice:
        console.print("[bold yellow]⚠️ Operación cancelada por el usuario.[/bold yellow]")
        return
        
    key, selected_data = keys_map[selected_choice]
    
    # 2. Selección de Workflow
    console.print("\n[bold green]🧬 PASO 2: Seleccione el Workflow de Diseño[/bold green]")
    workflow_choice = questionary.select(
        "Metodología de generación molecular:",
        choices=[
            "De Novo Design (Scaffold Hopping a partir de esqueletos genéricos)",
            "Lead Optimization (Optimización y mutaciones de molécula de partida)",
            "Drug Repurposing (Semillas activas desde ChEMBL + optimización BRICS)"
        ]
    ).ask()

    if not workflow_choice:
        return

    if "De Novo" in workflow_choice:
        workflow_mode = "de_novo"
    elif "Lead Optimization" in workflow_choice:
        workflow_mode = "lead_opt"
    else:
        workflow_mode = "repurposing"
    parent_smiles = None
    
    if workflow_mode == "lead_opt":
        console.print("\n[bold green]✏️ PASO 2b: Ingrese la Molécula de Partida (SMILES)[/bold green]")
        
        # Presets recomendados según diana
        presets = {
            "EGFR": "COc1cc2ncnc(Nc3ccc(F)cc3Cl)c2cc1OC3CCN(C)CC3", # Gefitinib
            "DPP4": "C1CN(C(=O)C(C1)N)C2CC(C(C2)F)(F)F", # Sitagliptin-like fragment
            "MPRO": "CC(C)CC(NC(=O)C(Cc1ccccc1)NC(=O)C)C(=O)NC(C)C(=O)O" # Peptídico
        }
        target_name = selected_data["target"]
        default_smiles = presets.get(target_name, "c1ccccc1")
        
        parent_smiles = questionary.text(
            f"Cadena SMILES de partida (Preset sugerido para {target_name}: '{default_smiles}'):",
            default=default_smiles
        ).ask()
        
        if not parent_smiles:
            console.print("[bold red]❌ Se requiere un SMILES padre válido para Lead Optimization.[/bold red]")
            return
            
        # Validación básica RDKit
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(parent_smiles)
            if mol is None:
                raise ValueError("Invalido")
        except Exception:
            console.print("[bold red]❌ SMILES inválido químicamente. Abortando.[/bold red]")
            return
            
        # Validar frente a Guardrails de seguridad
        from utils.guardrails import validate_molecular_safety
        is_safe, reason = validate_molecular_safety(parent_smiles)
        if not is_safe:
            console.print(Panel(
                f"[bold red]🚨 ALERTA DE BIOSEGURIDAD ACTIVADA[/bold red]\n\n"
                f"La molécula de partida ingresada ha sido rechazada por el sistema de guardrails:\n"
                f"[yellow]{reason}[/yellow]\n\n"
                f"No está permitido sintetizar, optimizar ni simular compuestos de abuso o agentes químicos nocivos.",
                title="ERROR DE SEGURIDAD ESTRUCTURAL",
                border_style="red"
            ))
            return
            
    # 3. Parámetros de Simulación y Ejecución
    console.print("\n[bold green]⚙️ PASO 3: Configuración de la Simulación[/bold green]")
    iterations = questionary.text(
        "Número de iteraciones del loop de diseño cerrado (planner-generator-dock-reflect):",
        default="10"
    ).ask()
    
    try:
        iterations = int(iterations)
    except ValueError:
        iterations = 10
        
    docking_mode_choice = questionary.select(
        "Modo de Simulación de Docking:",
        choices=[
            "Simulación Hashing Determinista (Mock - Ultra rápido, ideal para testing)",
            "AutoDock Vina Local Nativo (Cálculos de energía de unión reales)"
        ]
    ).ask()
    
    docking_mode = "mock" if "Simulación Hashing" in docking_mode_choice else "real"
    
    # Mostrar resumen
    clear_screen()
    show_banner()
    
    summary_table = Table(title="[bold cyan]Configuración de Misión Farmacológica[/bold cyan]", border_style="cyan")
    summary_table.add_column("Parámetro", style="bold yellow")
    summary_table.add_column("Configuración", style="white")
    
    summary_table.add_row("Área Terapéutica", selected_data["display_name"])
    summary_table.add_row("Target Genómico", selected_data["target"])
    summary_table.add_row("Receptor PDB ID", selected_data["pdb_id"])
    summary_table.add_row("Modo de Workflow", "Lead Optimization 🧬" if workflow_mode == "lead_opt" else "De Novo Design 🆕")
    if parent_smiles:
        summary_table.add_row("SMILES Padre", parent_smiles)
    summary_table.add_row("Iteraciones del Loop", str(iterations))
    summary_table.add_row("Simulador de Docking", "AutoDock Vina (Nativo Windows)" if docking_mode == "real" else "Simulado Reproducible (QSAR-mock)")
    
    console.print(summary_table)
    
    console.print(Panel(
        f"[bold yellow]⚠️ EXENCIÓN DE RESPONSABILIDAD (DISCLAIMER):[/bold yellow]\n"
        f"{selected_data['disclaimer']}",
        border_style="yellow",
        title="[bold yellow]AVISO CIENTÍFICO[/bold yellow]"
    ))
    
    confirm = questionary.confirm("¿Desea iniciar la misión terapéutica con estos parámetros?").ask()
    if not confirm:
        console.print("[bold yellow]⚠️ Ejecución abortada.[/bold yellow]")
        return
        
    # Lanzar la corrida
    console.print("\n[bold green]🚀 Iniciando DrugAgent en segundo plano... Espere por favor.[/bold green]\n")
    
    cmd = [
        "python", "run_agent.py",
        "--target", selected_data["target"],
        "--pdb", selected_data["pdb_id"],
        "--iterations", str(iterations),
        "--workflow", workflow_mode,
        "--area", selected_data["display_name"].split(":")[0].strip(),
        "--indication", selected_data["display_name"].split(":")[1].strip()
    ]
    if parent_smiles:
        cmd.extend(["--parent-smiles", parent_smiles])
        
    try:
        # Ejecutar el comando del agente y streamear stdout en tiempo real de forma premium
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Ejecutando misión en bucle cerrado ({iterations} iteraciones)...[/cyan]", total=iterations)
            
            env_map = {**os.environ, "DOCKING_MODE": docking_mode}
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                env=env_map
            )
            
            # Leer stdout en tiempo real y mostrar las líneas más importantes
            last_iteration_seen = 0
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                
                # Mostrar en consola
                if "GENERATOR:" in line_str or "SIMULATOR:" in line_str or "ANALYZER:" in line_str or "REFLECTOR:" in line_str:
                    console.print(f"[bold cyan]🔬[/bold cyan] {line_str}")
                elif "GUARDRAIL" in line_str:
                    console.print(f"[bold red]🚨[/bold red] [red]{line_str}[/red]")
                elif "MEJORES CANDIDATOS:" in line_str or "SMILES:" in line_str or "Score:" in line_str or "QED:" in line_str:
                    console.print(f"[bold green]✨[/bold green] {line_str}")
                elif "Iteración" in line_str or "Iter " in line_str or "Iteracion" in line_str:
                    # Parsear iteración actual
                    try:
                        # ej: "[Iter 3] Generator"
                        if "Iter " in line_str:
                            it_num = int(line_str.split("Iter ")[1].split("]")[0])
                            if it_num > last_iteration_seen:
                                progress.advance(task, it_num - last_iteration_seen)
                                last_iteration_seen = it_num
                    except Exception:
                        pass
                    console.print(f"[bold yellow]🔄[/bold yellow] {line_str}")
                elif "ERROR" in line_str:
                    console.print(f"[bold red]❌ {line_str}[/bold red]")
                else:
                    # Mostrar logs genéricos de forma sutil
                    if len(line_str) < 120 and "..." not in line_str:
                        console.print(f"[dim]{line_str}[/dim]")
            
            process.wait()
            progress.update(task, completed=iterations)
            
        if process.returncode == 0:
            console.print("\n[bold green]🎉 ¡Misión Terapéutica Completada Exitosamente! 🎉[/bold green]")
            console.print("[bold green]Se ha generado el reporte científico en formato PDF en el directorio principal.[/bold green]")
            console.print("[bold green]Todos los datos han sido persistidos de forma segura en Prisma DB.[/bold green]\n")
        else:
            console.print(f"\n[bold red]❌ El agente terminó con código de error {process.returncode}. Revise los logs en 'output/agent.log'[/bold red]\n")
            
    except Exception as e:
        console.print(f"[bold red]❌ Error de ejecución: {e}[/bold red]")
            
    input("Presione ENTER para continuar...")

def run_autonomous_simulation():
    console.print("\n[bold magenta]🤖 Iniciando Simulación de Descubrimiento 100% Autónomo...[/bold magenta]")
    console.print("[dim]Presione Ctrl+C en cualquier momento para detener la simulación y regresar al menú.[/dim]\n")
    import subprocess
    try:
        # Ejecutar de forma interactiva en la misma consola
        subprocess.run(["python", "run_autonomous.py"])
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 Retornando al menú de control...[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]❌ Error al ejecutar run_autonomous.py: {e}[/bold red]")
    input("\nPresione ENTER para continuar...")

def start_dashboard():
    console.print("\n[bold green]📊 Iniciando Dashboard Científico en segundo plano...[/bold green]")
    console.print("[dim]Ejecutando: streamlit run ui/dashboard.py[/dim]\n")
    import subprocess
    try:
        # En Windows, usar subprocess.Popen con shell=True para no bloquear
        subprocess.Popen("streamlit run ui/dashboard.py", shell=True)
        console.print("[bold green]✅ Servidor Streamlit iniciado.[/bold green]")
        try:
            import webbrowser
            import time
            time.sleep(1.5)
            webbrowser.open("http://localhost:8501")
        except Exception:
            pass
    except Exception as e:
        console.print(f"[bold red]❌ No se pudo iniciar Streamlit: {e}[/bold red]")
    input("\nPresione ENTER para regresar al menú...")

def start_mlflow_ui():
    console.print("\n[bold green]📈 Iniciando MLflow Telemetry UI en segundo plano...[/bold green]")
    console.print("[dim]Ejecutando: mlflow ui --backend-store-uri sqlite:///./data/mlflow.db --port 5000[/dim]\n")
    import subprocess
    import os
    try:
        env = {**os.environ, "MLFLOW_TRACKING_URI": "sqlite:///./data/mlflow.db"}
        subprocess.Popen("mlflow ui --backend-store-uri sqlite:///./data/mlflow.db --port 5000", shell=True, env=env)
        console.print("[bold green]✅ Servidor MLflow iniciado con éxito.[/bold green]")
        console.print("[bold cyan]🔗 URL: http://127.0.0.1:5000[/bold cyan]")
        try:
            import webbrowser
            import time
            time.sleep(1.5)
            webbrowser.open("http://127.0.0.1:5000")
        except Exception:
            pass
    except Exception as e:
        console.print(f"[bold red]❌ No se pudo iniciar MLflow: {e}[/bold red]")
    input("\nPresione ENTER para regresar al menú...")

def run_system_diagnostics():
    clear_screen()
    show_banner()
    console.print("\n[bold cyan]🩺 DIAGNÓSTICO DE ENTORNO Y SISTEMAS - DRUGAGENT[/bold cyan]\n")
    
    # 1. Verificar RDKit
    try:
        import rdkit
        from rdkit import Chem
        rdkit_status = f"[green]✅ Disponible (versión {rdkit.__version__})[/green]"
    except ImportError as e:
        rdkit_status = f"[red]❌ No disponible ({e})[/red]"
        
    # 2. Verificar SQLite y Prisma Connection
    try:
        from orchestrator.db import db, init_db, close_db
        init_db()
        run_count = db.run.count()
        cand_count = db.candidate.count()
        db_status = f"[green]✅ Conectada (SQLite). {run_count} Corridas, {cand_count} Candidatos en BD.[/green]"
        close_db()
    except Exception as e:
        db_status = f"[red]❌ Error de conexión con SQLite ({e})[/red]"
        
    # 3. Verificar API Keys
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    
    groq_status = "[green]✅ Configurada[/green]" if (groq_key and not groq_key.startswith("gsk_REEMPLAZA")) else "[yellow]⚠️ No configurada u genérica[/yellow]"
    gemini_status = "[green]✅ Configurada[/green]" if (gemini_key and not gemini_key.startswith("AIzaSyBFlOj")) else "[green]✅ Configurada (Gemini Activa)[/green]" if gemini_key else "[yellow]⚠️ No configurada o genérica[/yellow]"
    
    # 4. Verificar Vina EXE
    from core.docking import VINA_EXE
    vina_status = f"[green]✅ Disponible en {VINA_EXE}[/green]" if VINA_EXE.exists() else f"[yellow]⚠️ No disponible (se usará Mock Docking)[/yellow]"
    
    # 5. Modo Offline
    offline_mode = os.environ.get("OFFLINE_MODE", "False")
    offline_status = f"[bold magenta]ACTIVO ({offline_mode})[/bold magenta]" if offline_mode.lower() in ["true", "1", "yes"] else f"[green]Inactivo ({offline_mode})[/green]"

    console.print(f" • [bold]RDKit Química Local:[/bold]      {rdkit_status}")
    console.print(f" • [bold]Base de Datos Prisma SQLite:[/bold] {db_status}")
    console.print(f" • [bold]Clave de API Groq:[/bold]          {groq_status}")
    console.print(f" • [bold]Clave de API Gemini:[/bold]        {gemini_status}")
    console.print(f" • [bold]AutoDock Vina local:[/bold]        {vina_status}")
    console.print(f" • [bold]Modo Offline Autónomo:[/bold]      {offline_status}")
    
    input("\nPresione ENTER para regresar al menú...")

def view_mission_history():
    clear_screen()
    show_banner()
    console.print("\n[bold cyan]📜 HISTORIAL DE MISIONES DE DRUGAGENT[/bold cyan]\n")
    try:
        from orchestrator.db import db, init_db, close_db
        from rich.table import Table
        init_db()
        runs = db.run.find_many(order={"start_time": "desc"}, take=15)
        if not runs:
            console.print("[yellow]No se encontraron corridas en la base de datos.[/yellow]")
        else:
            table = Table(title="Últimas 15 Misiones de Descubrimiento", border_style="cyan")
            table.add_column("ID", style="cyan")
            table.add_column("Diana / PDB", style="green")
            table.add_column("Área Terapéutica / Indicación", style="yellow")
            table.add_column("Workflow", style="magenta")
            table.add_column("Docking", style="blue")
            table.add_column("Estado", style="bold")
            table.add_column("Duración", style="dim")
            table.add_column("MLflow Run", style="cyan dim")
            
            for r in runs:
                status_color = "green" if r.status == "completed" else ("red" if r.status == "failed" else "yellow")
                status_str = f"[{status_color}]{r.status.upper()}[/{status_color}]"
                
                dur_str = f"{r.duration_sec:.1f}s" if r.duration_sec is not None else "-"
                dock_mode = r.docking_mode if r.docking_mode else "auto"
                
                mlflow_run = "-"
                if hasattr(r, 'mlflow_run_id') and r.mlflow_run_id:
                    mlflow_run = r.mlflow_run_id[:8] + "..."
                
                table.add_row(
                    str(r.id),
                    f"{r.target_name} ({r.target_pdb_id})",
                    f"{r.therapeutic_area}\n[dim]{r.indication_label}[/dim]",
                    r.workflow_mode,
                    dock_mode,
                    status_str,
                    dur_str,
                    mlflow_run
                )
            console.print(table)
        close_db()
    except Exception as e:
        console.print(f"[bold red]❌ Error al consultar la base de datos: {e}[/bold red]")
    input("\nPresione ENTER para continuar...")

def test_biological_guardrails():
    clear_screen()
    show_banner()
    console.print("\n[bold red]🛡️ PRUEBA AISLADA DE GUARDRAILS BIOLÓGICOS (RDKit)[/bold red]\n")
    smiles = questionary.text(
        "Ingrese un SMILES para evaluar contra los guardrails (ej: CCO, CC(=O)Oc1ccccc1C(=O)O):",
        default="CC(=O)Oc1ccccc1C(=O)O"
    ).ask()
    
    if not smiles:
        return
        
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, Crippen, rdMolDescriptors, QED
        
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            console.print(f"[bold red]❌ El SMILES ingresado no es válido para RDKit.[/bold red]")
            input("\nPresione ENTER para continuar...")
            return
            
        mw = Descriptors.ExactMolWt(mol)
        logp = Crippen.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rotbonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
        qed = QED.qed(mol)
        
        # Filtro de Lipinski
        passed = (
            mw <= 500 and
            logp <= 5.0 and
            hbd <= 5 and
            hba <= 10 and
            tpsa <= 140.0 and
            rotbonds <= 10
        )
        
        console.print(f"\n[bold green]Propiedades físico-químicas calculadas para:[/bold green] [yellow]{smiles}[/yellow]")
        console.print(f" • Peso Molecular (MW):   [cyan]{mw:.2f}[/cyan] (Límite: <= 500)")
        console.print(f" • LogP (Octanol/Agua):  [cyan]{logp:.2f}[/cyan] (Límite: <= 5.0)")
        console.print(f" • Donadores H (HBD):    [cyan]{hbd}[/cyan] (Límite: <= 5)")
        console.print(f" • Aceptores H (HBA):     [cyan]{hba}[/cyan] (Límite: <= 10)")
        console.print(f" • Superficie Polar (TPSA):[cyan]{tpsa:.2f}[/cyan] (Límite: <= 140.0)")
        console.print(f" • Enlaces Rotables:      [cyan]{rotbonds}[/cyan] (Límite: <= 10)")
        console.print(f" • Índice QED (Belleza):  [cyan]{qed:.4f}[/cyan]")
        
        if passed:
            console.print(f"\n[bold green]✅ ¡APROBADO! La molécula cumple con la Regla de 5 de Lipinski y Veber.[/bold green]")
        else:
            console.print(f"\n[bold red]❌ ¡RECHAZADO! La molécula viola uno o más criterios de los Guardrails.[/bold red]")
            
    except Exception as e:
        console.print(f"[bold red]Error al ejecutar los guardrails: {e}[/bold red]")
        
    input("\nPresione ENTER para continuar...")

if __name__ == "__main__":
    while True:
        clear_screen()
        show_banner()
        console.print("[bold cyan]Menú Principal de Control:[/bold cyan]")
        console.print(" [1] 🔬 Lanzar Misión Terapéutica (Cerrar Loop de Diseño)")
        console.print(" [2] 🤖 Lanzar Simulación de Descubrimiento 100% Autónomo")
        console.print(" [3] 📊 Iniciar Dashboard Científico (Streamlit)")
        console.print(" [4] 🩺 Diagnóstico de Entorno y Sistemas")
        console.print(" [5] 📜 Ver Historial de Misiones Realizadas")
        console.print(" [6] 🛡️ Ejecutar Test de Guardrails Biológicos")
        console.print(" [7] 📈 Iniciar / Abrir MLflow Telemetry UI")
        console.print(" [8] 🚪 Salir")
        
        opt = questionary.text("Seleccione una opción (1-8):", default="1").ask()
        if opt == "1":
            run_agent_workflow()
        elif opt == "2":
            run_autonomous_simulation()
        elif opt == "3":
            start_dashboard()
        elif opt == "4":
            run_system_diagnostics()
        elif opt == "5":
            view_mission_history()
        elif opt == "6":
            test_biological_guardrails()
        elif opt == "7":
            start_mlflow_ui()
        elif opt == "8":
            console.print("[bold green]👋 Saliendo de DrugAgent-Local. ¡Buen día científico![/bold green]")
            break

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from io import BytesIO
import locale

# Configurar la localización en español
# locale.setlocale(locale.LC_ALL, 'es_ES.UTF-8')

try:
    locale.setlocale(locale.LC_ALL, 'es_ES.UTF-8')
except locale.Error:
    # Fallback to default locale
    locale.setlocale(locale.LC_ALL, '')

def generate_excel_data(df_numeric, birth_date):
    """Generate Excel data for download"""
    csv = df_numeric.copy()
    
    # Asegurarse de que la columna Fecha sea datetime
    if not pd.api.types.is_datetime64_any_dtype(csv['Fecha']):
        csv['Fecha'] = pd.to_datetime(csv['Fecha'])
    
    # Extraer año, mes y calcular edad
    csv['Año'] = csv['Fecha'].dt.year  # Año como número entero
    
    # Mapear el mes a su nombre en español
    months_es = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
        7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    csv['Mes'] = csv['Fecha'].dt.month.map(months_es)
    
    # Calcular edad para cada fecha
    csv['EDAD'] = csv['Fecha'].apply(
        lambda x: (x.year - birth_date.year) - ((x.month, x.day) < (birth_date.month, birth_date.day))
    )
    
    # Formatear la columna Fecha para el CSV
    csv['Fecha'] = csv['Fecha'].dt.strftime('%Y-%m-%d')
    
    # Reordenar columnas para que Año, Mes y Edad estén al principio
    cols = ['Año', 'Mes', 'EDAD'] + [col for col in csv.columns if col not in ['Año', 'Mes', 'EDAD', 'Fecha']] + ['Fecha']
    csv = csv[cols]
    
    # Generar Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Formatear el Excel
        csv.to_excel(writer, index=False, sheet_name='Calculo_ERE')
        workbook = writer.book
        worksheet = writer.sheets['Calculo_ERE']
        
        # Ajustar el ancho de las columnas
        for i, col in enumerate(csv.columns):
            max_length = max(csv[col].astype(str).apply(len).max(), len(col)) + 2
            worksheet.set_column(i, i, min(max_length, 20))
        
        # Aplicar formato de moneda a las columnas numéricas
        money_format = workbook.add_format({'num_format': '#,##0.00 €'})
        for col_num, column in enumerate(csv.columns):
            if column not in ['Año', 'Mes', 'EDAD', 'Fecha', 'Tasa IRPF TESA (%)', 'Tasa IRPF SEPE (%)', 'Limitación 360 días aplicada']:
                worksheet.set_column(col_num, col_num, None, money_format)
    
    return output.getvalue()

def calculate_mixed_compensation(employment_start_date, exit_date, annual_salary):
    """
    Calcula la indemnización mixta para contratos firmados antes del 12 de febrero de 2012.
    Aplica 45 días por año trabajado para periodo anterior a esa fecha y 33 días para periodo posterior.
    """
    # Fecha clave: 11 de febrero de 2012
    key_date = date(2012, 2, 11)
    
    # Verificar si el contrato es anterior a la fecha clave
    #if employment_start_date >= key_date:
    #    return 0, 0, 0, "No aplica indemnización mixta (contrato posterior al 12/02/2012)"
    
    # Calcular salario diario
    daily_salary = annual_salary / 365
    
    # Periodo 1: Desde incorporación hasta 12/02/2012 (45 días/año)
    period1_start = employment_start_date
    period1_end = min(key_date, exit_date)
    
    if period1_end <= period1_start:
        period1_days = 0
        period1_years = 0
    else:
        period1_days = (period1_end - period1_start).days
        period1_years = period1_days / 365
    
    # Periodo 2: Desde 13/02/2012 hasta fecha de salida (33 días/año)
    period2_start = max(key_date, employment_start_date)
    period2_end = exit_date
    
    if period2_end <= period2_start:
        period2_days = 0
        period2_years = 0
    else:
        period2_days = (period2_end - period2_start).days
        period2_years = period2_days / 365
    
    # Calcular indemnización para cada periodo
    period1_compensation = period1_years * 45 * daily_salary
    period2_compensation = period2_years * 33 * daily_salary

    total_compensation = period1_compensation + period2_compensation

    
    # Calcular total de días trabajados
    total_days_worked = (exit_date - employment_start_date).days if exit_date > employment_start_date else 0
    
    # Aplicar límite: nunca mayor que el cálculo anterior para los primeros 360 días del periodo total
    total_years = total_days_worked / 365
    
    # period1_compensation + period2_compensation_limitada
    # donde period2_compensation_limitada no sea mayor que la correspondiente a (2 años menos period1_years) a 33 días/año
    max_period2_years = max(0, 2 - period1_years * 45 / 365)  # No puede ser negativo
    max_period2_compensation = max_period2_years * 33 * daily_salary
    period2_compensation_limited = min(period2_compensation, max_period2_compensation)

    # max_compensation_730 = period1_compensation + period2_compensation_limited
    
    # Aplicar límite
    if (period1_years * 45 + period2_years * 33) > 730:
        # total_compensation = period1_compensation + (730 - period1_years * 45) * daily_salary
        total_compensation = period1_compensation + max_period2_years * 33 * daily_salary
        limitation_applied = True
    else:
        total_compensation = period1_compensation + period2_compensation
        limitation_applied = False
    
    return round(total_compensation, 2), round(period1_compensation, 2), round(period2_compensation, 2), limitation_applied

def calculate_salary_evolution(birth_date, exit_date, annual_salary, fiscal_exemption, irpf_tasa, sepe_salary, irpf_sepe, retirement_salary_63, retirement_salary_65, irpf_jubilacion):
    # Convertir porcentajes a decimales
    irpf_tasa = irpf_tasa / 100
    irpf_sepe = irpf_sepe / 100
    
    # Calcular fechas importantes
    date_63 = birth_date + relativedelta(years=63)
    date_65 = birth_date + relativedelta(years=65)
    # end_date = date_65 + relativedelta(months=12)  # 12 meses después de cumplir 65
    end_date = date_65  # Cumplidos los 65
    
    # Inicializar listas para almacenar los resultados
    dates = []
    tesa_gross_list = []
    tesa_net_list = []
    sepe_gross_list = []
    sepe_net_list = []
    pension_gross_list = []
    pension_net_list = []
    total_net_list = []
    irpf_tasa_list = []
    irpf_sepe_rate_list = []
    irpf_pension_rate_list = []
    irpf_tesa_applied_list = []
    irpf_sepe_applied_list = []
    irpf_pension_applied_list = []
    accumulated_taxable_income_list = []
    
    current_date = exit_date
    month_count = 0
    accumulated_taxable_income = 0
    fiscal_exemption_reached = False
    
    # Calcular hasta 12 meses después de los 65 años
    while current_date <= end_date:
        # 1. Calcular salario SEPE (solo primeros 24 meses)
        if month_count < 24:
            sepe_gross = sepe_salary
            # Calcular IRPF SEPE (5% por defecto)
            sepe_irpf = sepe_gross * irpf_sepe
            sepe_net = sepe_gross - sepe_irpf
        else:
            sepe_gross = 0
            sepe_irpf = 0
            sepe_net = 0
        
        # 2. Calcular salario TESA bruto
        # Calcular incremento anual del 1% hasta 2033
        years_since_start = (current_date.year - exit_date.year) + (current_date.month - exit_date.month) / 12
        max_year = 2033
        current_year = current_date.year
        
        # Calcular el factor de incremento (1% por año hasta 2033)
        if current_year <= max_year:
            increment_factor = (1.01) ** min(years_since_start, (max_year - exit_date.year))
        else:
            increment_factor = (1.01) ** (max_year - exit_date.year)  # Mantener el último incremento después de 2033
        
        if current_date < date_63:
            tesa_gross = (annual_salary * 0.68) / 12 - sepe_gross
        elif current_date < date_65:
            tesa_gross = (annual_salary * 0.38 * increment_factor) / 12 - sepe_gross
        else:
            # Después de los 65 años, aplicar el salario mensual de jubilación a los 65
            tesa_gross = 0
        
        # 3. Calcular IRPF TESA (solo después de alcanzar la exención fiscal)
        accumulated_taxable_income += tesa_gross
        if not fiscal_exemption_reached:
            if accumulated_taxable_income >= fiscal_exemption:
                fiscal_exemption_reached = True
                remaining_exemption = accumulated_taxable_income - fiscal_exemption
                tesa_irpf = remaining_exemption * irpf_tasa
            else:
                tesa_irpf = 0
        else:
            tesa_irpf = tesa_gross * irpf_tasa
        
        tesa_net = tesa_gross - tesa_irpf
        
        # 4. Calcular pensión bruta y neta
        if current_date >= date_63:
            pension_gross = retirement_salary_63 if retirement_salary_63 > 0 else retirement_salary_65
            # Duplicar la pensión en junio (6) y noviembre (11)
            if current_date.month in [6, 11]:
                pension_gross *= 2
            pension_irpf = pension_gross * (irpf_jubilacion / 100)
            pension_net = pension_gross - pension_irpf
        else:
            pension_gross = 0
            pension_irpf = 0
            pension_net = 0
        
        # 5. Calcular total neto
        total_net = tesa_net + sepe_net + pension_net
        
        # Añadir a las listas
        dates.append(current_date)
        tesa_gross_list.append(round(tesa_gross, 2))
        tesa_net_list.append(round(tesa_net, 2))
        sepe_gross_list.append(round(sepe_gross, 2))
        sepe_net_list.append(round(sepe_net, 2))
        pension_gross_list.append(round(pension_gross, 2))
        pension_net_list.append(round(pension_net, 2))
        total_net_list.append(round(total_net, 2))
        irpf_tesa_applied_list.append(round(tesa_irpf, 2))
        irpf_sepe_applied_list.append(round(sepe_irpf, 2))
        irpf_pension_applied_list.append(round(pension_irpf, 2))
        irpf_tasa_list.append(irpf_tasa * 100)  # Convertir a porcentaje
        irpf_sepe_rate_list.append(irpf_sepe * 100)  # Convertir a porcentaje
        irpf_pension_rate_list.append(irpf_jubilacion)  # Ya está en porcentaje
        accumulated_taxable_income_list.append(round(accumulated_taxable_income, 2))
        
    
        # Avanzar al siguiente mes
        current_date = current_date + relativedelta(months=1)
        month_count += 1
    
    # Crear DataFrame primero con las fechas originales
    df = pd.DataFrame({
        'Fecha': dates,
        'TESA Bruto': tesa_gross_list,
        'Acumulado Tributable': accumulated_taxable_income_list,
        'Tasa IRPF TESA (%)': irpf_tasa_list,
        'IRPF TESA': irpf_tesa_applied_list,
        'TESA Neto': tesa_net_list,
        'SEPE Bruto': sepe_gross_list,
        'Tasa IRPF SEPE (%)': irpf_sepe_rate_list,
        'IRPF SEPE': irpf_sepe_applied_list,
        'SEPE Neto': sepe_net_list,
        'Pensión Bruta': pension_gross_list,
        'Tasa IRPF Pensión (%)': irpf_pension_rate_list,
        'IRPF Pensión': irpf_pension_applied_list,
        'Pensión Neta': pension_net_list,
        'Total Neto': total_net_list
    })
    
    # Guardar una copia del DataFrame con los valores numéricos para los cálculos
    df_numeric = df.copy()
    
    # Formatear columnas monetarias a euros españoles solo para visualización
    monetary_columns = [
        'TESA Bruto', 'Acumulado Tributable', 'IRPF TESA', 'TESA Neto',
        'SEPE Bruto', 'IRPF SEPE', 'SEPE Neto',
        'Pensión Bruta', 'IRPF Pensión', 'Pensión Neta', 'Total Neto'
    ]
    
    for col in monetary_columns:
        df[col] = df[col].apply(lambda x: f"{float(x):,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))
    
    # Crear columnas de Año y Mes
    months_es = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
        7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    
    # Crear una copia de la columna Fecha para formatear
    formatted_dates = df['Fecha'].copy()
    
    # Crear columnas de Año, Mes y Edad
    df['Año'] = df['Fecha'].apply(lambda x: f"{x.year:,}".replace(',', '.'))  # Año con separador de miles
    df['Mes'] = df['Fecha'].apply(lambda x: months_es[x.month])
    
    # Calcular edad para cada fecha
    df['EDAD'] = df['Fecha'].apply(
        lambda x: (x.year - birth_date.year) - ((x.month, x.day) < (birth_date.month, birth_date.day))
    )
    
    # Mover las columnas Año, Mes y Edad al principio del DataFrame
    cols = ['Año', 'Mes', 'EDAD'] + [col for col in df.columns if col not in ['Año', 'Mes', 'EDAD', 'Fecha']]
    df = df[cols]
    
    # Agregar la columna Fecha formateada al final
    df['Fecha'] = formatted_dates.apply(lambda x: f"{x.year} {months_es[x.month]}")
    
    # Devolver tanto el DataFrame formateado como el numérico
    return df, df_numeric

def main():
    st.set_page_config(page_title="Calculadora ERE España", layout="wide")
    
    # Custom CSS to style the sidebar
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] {
                background-color: blue;
            }
            [data-testid="stSidebar"] .st-emotion-cache-6qob1r {
                background-color: blue;
            }
            [data-testid="stSidebar"] * {
                color: white !important;
            }
            [data-testid="stSidebar"] input, 
            [data-testid="stSidebar"] button,
            [data-testid="stSidebar"] .stButton > button,
            [data-testid="stSidebar"] .stDateInput,
            [data-testid="stSidebar"] .stNumberInput,
            [data-testid="stSidebar"] .stSelectbox {
                color: black !important;
            }
            [data-testid="stSidebar"] button span,
            [data-testid="stSidebar"] .stButton > button span,
            [data-testid="stSidebar"] button div,
            [data-testid="stSidebar"] .stButton > button div,
            [data-testid="stSidebar"] button p,
            [data-testid="stSidebar"] .stButton > button p,
            [data-testid="stSidebar"] button * {
                color: black !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    st.title("Calculadora de ERE en España")
    
    # Add Excel download button in top-right
    col1, col2, col3 = st.columns([2, 1, 1])
    with col3:
        # This button will be populated later with Excel data
        excel_download_placeholder = st.empty()
    
    # Sidebar con los inputs
    with st.sidebar:
        st.header("Parámetros de Entrada")
        
        # Botón de recarga en la parte superior
        if st.button("🔄 Recargar Valores por Defecto", use_container_width=True, help="Recarga la página con todos los valores por defecto"):
            # Establecer valores por defecto en session_state
            st.session_state.birth_date = date(1970, 3, 25)
            st.session_state.employment_start_date = date(1989, 6, 1)
            st.session_state.exit_date = date(2026, 3, 1)
            st.session_state.annual_salary = 65919.12
            st.session_state.irpf_tasa = 13.75
            st.session_state.sepe_salary = 1181.0
            st.session_state.irpf_sepe = 5.0
            st.session_state.retirement_age = "Jubilación a los 63 años"
            st.session_state.retirement_salary_63 = 3033.24
            st.session_state.retirement_salary_65 = 3100.00
            st.session_state.irpf_jubilacion = 23.0
            st.rerun()
        
       # st.divider()
        
        # Fecha de nacimiento (por defecto: 25/03/1970)
        birth_date = st.date_input(
            "Fecha de Nacimiento",
            value=st.session_state.get('birth_date', date(1970, 3, 25)),
            min_value=date(1900, 1, 1),
            max_value=date.today(),
            key='birth_date'
        )
        
        # Fecha de incorporación a la empresa (por defecto: 01/06/2989)
        employment_start_date = st.date_input(
            "Fecha de Incorporación a la Empresa",
            value=st.session_state.get('employment_start_date', date(1989, 6, 1)),
            min_value=date(1900, 1, 1),
            max_value=date.today(),
            key='employment_start_date'
        )
        
        # Fecha de salida (por defecto: 01/03/2026)
        exit_date = st.date_input(
            "Fecha de Salida",
            value=st.session_state.get('exit_date', date(2026, 3, 1)),
            min_value=date(2000, 1, 1),
            max_value=date(2050, 12, 31),
            key='exit_date'
        )
        
        # Salario anual bruto (por defecto: 65.919,12€)
        annual_salary = st.number_input(
            "Salario Anual Bruto (€)",
            min_value=0.0,
            value=st.session_state.get('annual_salary', 65919.12),
            step=1000.0,
            key='annual_salary'
        )

        
        # IRPF TESA (por defecto: 13,75%)
        irpf_tasa = st.number_input(
            "IRPF TESA (%)",
            min_value=0.0,
            max_value=100.0,
            value=st.session_state.get('irpf_tasa', 13.75),
            step=0.01,
            key='irpf_tasa'
        )
        
        # Salario SEPE (por defecto: 1.181€)
        sepe_salary = st.number_input(
            "Salario SEPE (€)",
            min_value=0.0,
            value=st.session_state.get('sepe_salary', 1181.0),
            step=100.0,
            key='sepe_salary'
        )
        
        # IRPF SEPE (por defecto: 5%)
        irpf_sepe = st.number_input(
            "IRPF SEPE (%)",
            min_value=0.0,
            max_value=100.0,
            value=st.session_state.get('irpf_sepe', 5.0),
            step=0.1,
            key='irpf_sepe'
        )
        
        # Añadir inputs para jubilación
        # st.markdown("---")
        st.subheader("Parámetros de Jubilación")
        
        # Selector de edad de jubilación
        default_retirement = st.session_state.get('retirement_age', "Jubilación a los 63 años")
        retirement_age = st.radio(
            "Edad de jubilación",
            ["Jubilación a los 63 años", "Jubilación a los 65 años"],
            index=0 if default_retirement == "Jubilación a los 63 años" else 1,
            key='retirement_age'
        )
        
        # Mostrar el input correspondiente según la edad de jubilación seleccionada
        if retirement_age == "Jubilación a los 63 años":
            retirement_salary = st.number_input(
                "Pensión mensual por jubilación (€/mes)",
                min_value=0.0,
                value=st.session_state.get('retirement_salary_63', 3771.25),
                step=100.0,
                key="retirement_salary_63"
            )
            # Establecer el otro valor a 0 para que no afecte los cálculos
            retirement_salary_other = 0
        else:
            retirement_salary_other = st.number_input(
                "Pensión mensual por jubilación (€/mes)",
                min_value=0.0,
                value=st.session_state.get('retirement_salary_65', 4328.67),
                step=50.0,
                key="retirement_salary_65"
            )
            # Establecer el otro valor a 0 para que no afecte los cálculos
            retirement_salary = 0
        
        # IRPF Jubilación (por defecto: 23%)
        irpf_jubilacion = st.number_input(
            "IRPF Jubilación (%)",
            min_value=0.0,
            max_value=100.0,
            value=st.session_state.get('irpf_jubilacion', 23.0),
            step=0.5,
            key='irpf_jubilacion'
        )
    
    try:
        # Pasar los parámetros de jubilación correctos según la selección
        retirement_salary_63 = retirement_salary if retirement_age == "Jubilación a los 63 años" else 0
        retirement_salary_65 = retirement_salary_other if retirement_age == "Jubilación a los 65 años" else 0
        
        # Calcular ratio de exención 30%
        end_date_2035 = date(2035, 12, 31)
        days_worked = (exit_date - employment_start_date).days
        days_until_2035 = (end_date_2035 - exit_date).days
        
        # Asegurarse de que no haya división por cero y que los días sean positivos
        if days_until_2035 > 0:
            exemption_ratio = days_worked / days_until_2035
        else:
            exemption_ratio = 0
        
        # Ajustar IRPF TESA si el ratio es menor a 2
        if exemption_ratio < 2.0:
            irpf_tasa_applied = 30.0
        else:
            irpf_tasa_applied = irpf_tasa
        
        # Calcular indemnización mixta primero para obtener mixed_comp_total
        mixed_comp_total, mixed_comp_period1, mixed_comp_period2, mixed_comp_limitation = calculate_mixed_compensation(
            employment_start_date, exit_date, annual_salary
        )
        
        # Crear variable fiscal_exemption igual a mixed_comp_total
        fiscal_exemption = mixed_comp_total
                
        # Calcular la evolución salarial (obtenemos ambos DataFrames)
        df, df_numeric = calculate_salary_evolution(
            birth_date, exit_date, annual_salary, 
            fiscal_exemption, irpf_tasa_applied, sepe_salary, irpf_sepe,
            retirement_salary_63, retirement_salary_65, irpf_jubilacion
        )
        
        # Calcular Fecha de salida objetivo (ratio >= 2)
        target_exit_date = None
        # Iterar desde la fecha actual hasta 2035 para encontrar la fecha donde ratio >= 2
        current_check_date = max(exit_date, date.today())
        
        while current_check_date <= end_date_2035:
            days_worked_check = (current_check_date - employment_start_date).days
            days_until_2035_check = (end_date_2035 - current_check_date).days
            
            if days_until_2035_check > 0:
                exemption_ratio_check = days_worked_check / days_until_2035_check
                if exemption_ratio_check >= 2.0:
                    target_exit_date = current_check_date
                    break
            current_check_date = current_check_date + relativedelta(days=1)
        
        # Formatear la fecha objetivo para mostrar
        if target_exit_date:
            target_date_str = target_exit_date.strftime('%d/%m/%Y')
        else:
            target_date_str = 'No disponible'

        # Mostrar totales acumulados al inicio
        st.markdown('<h3 style="color:blue;">Totales Acumulados</h3>', unsafe_allow_html=True)
        total_months = len(df_numeric)
        total_tesa_net = df_numeric['TESA Neto'].sum()
        total_sepe_net = df_numeric['SEPE Neto'].sum()
        total_net = df_numeric['Total Neto'].sum()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Meses calculados", total_months)
        
        with col2:
            st.metric("Total TESA Neto", f"{total_tesa_net:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))
        
        with col3:
            st.metric("Total SEPE Neto", f"{total_sepe_net:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))
            
        with col4:
            st.metric("Total Neto", f"{total_net:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'), delta_color="off")
        
        # st.divider()

        # Mostrar resumen
        st.markdown('<h3 style="color:blue;">Resumen</h3>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Edad a la salida", f"{exit_date.year - birth_date.year} años")
            st.metric("Fecha de cálculo hasta", df['Fecha'].iloc[-1])

        with col2:
            st.metric(
            "Ratio Cálculo Exención 30%", 
            f"{exemption_ratio:.4f}",
            help=f"Días trabajados: {days_worked:,} / Días hasta 31/12/2035: {days_until_2035:,}"
            )
            st.metric(
            "Fecha de Salida Objetivo", 
            target_date_str,
            help="Fecha donde el ratio de exención >= 2"
            if target_exit_date else "No se encontró fecha con ratio >= 2"
            )
        
        with col3:
            st.metric("Tasa IRPF TESA", f"{irpf_tasa}%", help="Solo aplica si el ratio es >= 2")
            st.metric("Meses totales", len(df))

        
        with col4:
            st.metric("Tasa IRPF SEPE", f"{irpf_sepe}%")
        
        # Mostrar indemnización mixta
        st.markdown('<h3 style="color:blue;">Indemnización Mixta (Contratos anteriores al 12/02/2012)</h3>', unsafe_allow_html=True)
        
        if isinstance(mixed_comp_limitation, str):
            st.info(mixed_comp_limitation)
        else:
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("Periodo anterior a 12/02/2012", f"{mixed_comp_period1:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'), help="45 días por año trabajado")
            
            with col2:
                st.metric("Periodo posterior a 12/02/2012", f"{mixed_comp_period2:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'), help="33 días por año trabajado")
            
            with col3:
                st.metric("Indemnización Exenta IRPF", f"{mixed_comp_total:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'), delta_color="off", help="Indemnización total exenta IRPF, menor valor de 180.000€ y 24 meses")
            
            with col4:
                st.metric("Indemnización Calculada", f"{mixed_comp_period1 + mixed_comp_period2:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'), delta_color="off", help="Indemnización total calculada")

            with col5:
                if mixed_comp_limitation:
                    st.warning("⚠️ Límite de 24 meses aplicado")
                else:
                    st.success("✅ Sin limitación")

       

        
        # Mostrar tabla con los datos (excluyendo la última columna)
        st.subheader("Evolución Mensual")
        
        # Encontrar la primera fila donde IRPF TESA es mayor que cero
        df_display = df.iloc[:, :-1].copy()
        first_positive_irpf = None
        
        for idx, row in df_numeric.iterrows():
            if row['IRPF TESA'] > 0:
                first_positive_irpf = idx
                break
        
        # Aplicar estilo para resaltar la fila
        if first_positive_irpf is not None:
            def highlight_first_positive_irpf(row):
                if row.name == first_positive_irpf:
                    return ['background-color: #ffcccc'] * len(row)
                return [''] * len(row)
            
            styled_df = df_display.style.apply(highlight_first_positive_irpf, axis=1)
            st.dataframe(styled_df, height=400, width='stretch')
        else:
            st.dataframe(df_display, height=400, width='stretch')
        
        # Gráfico de evolución
        st.subheader("Evolución del Salario Neto")
        # Crear una columna de fecha formateada para el gráfico
        df_plot = df_numeric.copy()
        
        # Asegurarse de que la columna Fecha es de tipo datetime
        if not pd.api.types.is_datetime64_any_dtype(df_plot['Fecha']):
            df_plot['Fecha'] = pd.to_datetime(df_plot['Fecha'])
            
        # Crear columnas de fecha formateadas
        df_plot['Fecha_plot'] = df_plot['Fecha'].dt.strftime('%Y-%m')
        df_plot['Mes'] = df_plot['Fecha'].dt.strftime('%b %Y')  # Formato abreviado mes y año
        
        fig = px.line(
            df_plot,
            x='Mes', 
            y='Total Neto',
            title='Evolución del Salario Neto Mensual',
            labels={'Total Neto': 'Salario Neto (€)', 'Mes': 'Mes'},
            range_y=[0, df_numeric['Total Neto'].max() * 1.1]
        )
        
        # Actualizar el formato de los ejes y añadir grid
        fig.update_layout(
            xaxis=dict(
                showgrid=True,
                gridwidth=1,
                gridcolor='LightGrey',
                tickangle=-45,
                tickmode='auto',
                nticks=min(len(df_plot), 36),  # Máximo 36 meses para evitar saturación
                showline=True,
                linewidth=1,
                linecolor='black'
            ),
            yaxis=dict(
                showgrid=True,
                gridwidth=1,
                gridcolor='LightGrey',
                tickprefix='€',
                tickformat=',.2f',
                showline=True,
                linewidth=1,
                linecolor='black',
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor='Grey'
            ),
            plot_bgcolor='white',
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, width='stretch')
        
        # Resumen Anual
        st.subheader("Resumen Anual")
        
        # Crear resumen anual
        df_anual = df_numeric.copy()
        # Asegurarse de que la columna Fecha es de tipo datetime
        if not pd.api.types.is_datetime64_any_dtype(df_anual['Fecha']):
            df_anual['Fecha'] = pd.to_datetime(df_anual['Fecha'])
        df_anual['Año'] = df_anual['Fecha'].dt.year
        
        # Agrupar por año y sumar las columnas relevantes
        columnas_sumar = ['TESA Neto', 'SEPE Neto', 'Pensión Neta', 'Total Neto']
        resumen_anual = df_anual.groupby('Año')[columnas_sumar].sum().reset_index()
        
        # Formatear los valores para mostrar en la tabla
        resumen_mostrar = resumen_anual.copy()
        for col in columnas_sumar:
            resumen_mostrar[col] = resumen_mostrar[col].apply(lambda x: f"{x:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))
        
        # Mostrar la tabla de resumen anual
        st.dataframe(
            resumen_mostrar,
            column_config={
                'Año': 'Año',
                'TESA Neto': 'TESA Neto',
                'SEPE Neto': 'SEPE Neto',
                'Pensión Bruta': 'Pensión Bruta',
                'Pensión Neta': 'Pensión Neta',
                'Total Neto': 'Total Neto'
            },
            hide_index=True,
            width='stretch'
        )
        
        # Gráfico de barras del resumen anual
        st.subheader("Distribución Anual")
        
        # Preparar datos para el gráfico
        df_anual_plot = resumen_anual.melt(
            id_vars=['Año'],
            value_vars=['TESA Neto', 'SEPE Neto', 'Pensión Neta'],
            var_name='Concepto',
            value_name='Importe'
        )
        
        # Crear gráfico de barras apiladas
        fig_anual = px.bar(
            df_anual_plot,
            x='Año',
            y='Importe',
            color='Concepto',
            title='Distribución Anual por Concepto',
            labels={'Año': 'Año', 'Importe': 'Importe (€)', 'Concepto': 'Concepto'},
            barmode='stack'
        )
        
        # Formatear ejes
        fig_anual.update_yaxes(
            tickprefix='€',
            tickformat=',.2f',
            title_text='Importe (€)'
        )
        
        # Mostrar el gráfico
        st.plotly_chart(fig_anual, width='stretch')
                
        # Botón para descargar los resultados (usar df_numeric para mantener los valores numéricos)
        csv = df_numeric.copy()
                
        # Asegurarse de que la columna Fecha sea datetime
        if not pd.api.types.is_datetime64_any_dtype(csv['Fecha']):
            csv['Fecha'] = pd.to_datetime(csv['Fecha'])
        
        # Extraer año, mes y calcular edad
        csv['Año'] = csv['Fecha'].dt.year  # Año como número entero
        
        # Mapear el mes a su nombre en español
        months_es = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
            7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        csv['Mes'] = csv['Fecha'].dt.month.map(months_es)
        
        # Calcular edad para cada fecha
        csv['EDAD'] = csv['Fecha'].apply(
            lambda x: (x.year - birth_date.year) - ((x.month, x.day) < (birth_date.month, birth_date.day))
        )
        
        # Formatear la columna Fecha para el CSV
        csv['Fecha'] = csv['Fecha'].dt.strftime('%Y-%m-%d')
        
        # Reordenar columnas para que Año, Mes y Edad estén al principio
        cols = ['Año', 'Mes', 'EDAD'] + [col for col in csv.columns if col not in ['Año', 'Mes', 'EDAD', 'Fecha']] + ['Fecha']
        csv = csv[cols]
        
        # Crear dos columnas para los botones de descarga
        col1, col2 = st.columns(2)
        
        with col1:
            # Botón para descargar CSV
            csv_data = csv.to_csv(index=False, decimal=',', sep=';').encode('utf-8')
            st.download_button(
                label="📥 Descargar CSV",
                data=csv_data,
                file_name="calculo_ere.csv",
                mime="text/csv",
                width='stretch'
            )
            
        with col2:
            # Botón para descargar Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Formatear el Excel
                csv.to_excel(writer, index=False, sheet_name='Calculo_ERE')
                workbook = writer.book
                worksheet = writer.sheets['Calculo_ERE']
                
                # Ajustar el ancho de las columnas
                for i, col in enumerate(csv.columns):
                    max_length = max(csv[col].astype(str).apply(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(max_length, 20))
                
                # Aplicar formato de moneda a las columnas numéricas
                money_format = workbook.add_format({'num_format': '#,##0.00 €'})
                for col_num, column in enumerate(csv.columns):
                    if column not in ['Año', 'Mes', 'EDAD', 'Fecha', 'Tasa IRPF TESA (%)', 'Tasa IRPF SEPE (%)', 'Limitación 360 días aplicada']:
                        worksheet.set_column(col_num, col_num, None, money_format)
            
            excel_data = output.getvalue()
            st.download_button(
                label="📊 Descargar Excel",
                data=excel_data,
                file_name="calculo_ere.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch'
            )
        
    except Exception as e:
        st.error(f"Se produjo un error al calcular la evolución: {str(e)}")

if __name__ == "__main__":
    main()
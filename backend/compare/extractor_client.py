import pdfplumber
from backend.compare.schemas import (
    SetupStep,
    ClientExecutionStep,
    ClientScript,
)
from backend.compare.table_detection import identify_table_type
from backend.compare.text_parsers import normalize_text


def extract_client_pdf(pdf_path: str) -> ClientScript:
    setup_steps = []
    execution_steps = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()

            for table in tables:
                table_type = identify_table_type(table)

                # -------- SETUP --------
                if table_type == "setup":
                    for row in table[1:]:
                        if len(row) < 2:
                            continue
                        if str(row[0]).isdigit():
                            setup_steps.append(
                                SetupStep(
                                    step_number=int(row[0]),
                                    procedure=normalize_text(row[1]),
                                )
                            )

                # -------- EXECUTION --------
                elif table_type == "execution":
                    for row in table[1:]:
                        if len(row) < 3:
                            continue
                        if str(row[0]).isdigit():
                            execution_steps.append(
                                ClientExecutionStep(
                                    step_number=int(row[0]),
                                    procedure=normalize_text(row[1]),
                                    expected_results=normalize_text(row[2]),
                                )
                            )

    return ClientScript(setup_steps, execution_steps)
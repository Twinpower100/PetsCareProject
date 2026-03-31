"""
Общие утилиты экспорта для billing.
"""

import openpyxl
from django.http import HttpResponse


def build_excel_response(file_name, sheet_title, headers, rows):
    """
    Собирает XLSX-ответ для выгрузки отчетов и детализации счетов.
    """
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_title
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename={file_name}'
    workbook.save(response)
    return response

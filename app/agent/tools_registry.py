from app.tools.calculator import calculator_tool
from app.tools.consultar_tag import consultar_tag_tool
from app.tools.status_pims import status_pims_tool
from app.tools.tag_calculus import tag_calculus_tool
from app.tools.tag_statistics import tag_statistics_tool


# def get_calculator_tools():
#     return [
#     ]


def get_pims_tools():
    return [
        consultar_tag_tool,
        status_pims_tool,
        tag_statistics_tool,
        tag_calculus_tool,
    ]


def get_general_tools():
    return [
        # calculator_tool,
    ]
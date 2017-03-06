from supp.project import Project


def test_norm_package(project):
    project.add_m('testp.module')
    assert 'testp.module' == project.norm_package('.module', project.get_m('testp.tmodule'))
    assert 'testp' == project.norm_package('.', project.get_m('testp.tmodule'))


def test_import_of_compiled_modules():
    p = Project()
    m = p.get_module('datetime')
    assert 'timedelta' in m.attrs

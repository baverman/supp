def test_norm_package(project):
    project.add_m('testp.module')
    assert 'testp.module' == project.norm_package('.module', project.get_m('testp.tmodule'))
    assert 'testp' == project.norm_package('.', project.get_m('testp.tmodule'))

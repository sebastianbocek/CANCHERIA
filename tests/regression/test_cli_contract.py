from cancheria.cli import build_parser

def test_modern_cli_contract():
    p=build_parser()
    assert p.parse_args(["eval"]).command == "eval"
    args=p.parse_args(["run","--profile","./wa_profile"])
    assert args.profile == "./wa_profile"

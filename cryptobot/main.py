from cryptobot.config import from_env
from cryptobot.engine import BotEngine
from cryptobot.server import make_server


def main() -> None:
    config = from_env()
    engine = BotEngine(config)
    engine.start()

    server = make_server(engine, config.host, config.port)
    print(f"cryptobot running at http://{config.host}:{config.port} ({config.symbol} {config.interval})")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.stop()


if __name__ == "__main__":
    main()

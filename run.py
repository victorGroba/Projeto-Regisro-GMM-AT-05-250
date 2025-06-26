from app import create_app

app = create_app()
0
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True)
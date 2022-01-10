from fastapi import FastAPI

app = FastAPI()


@app.get("/hoge")
async def main():
    ...

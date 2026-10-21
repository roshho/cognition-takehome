FROM python:3.12-slim
WORKDIR /app
# platform package first so its install is cached separately
COPY packages/platform/python ./packages/platform/python
RUN pip install --no-cache-dir ./packages/platform/python
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/mockidp ./mockidp
COPY apps ./apps
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

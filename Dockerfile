# Используем официальный образ Python
FROM python:3.11-alpine
# Устанавливаем рабочую директорию в контейнере
WORKDIR ./
# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Устанавливаем зависимости
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r ./requirements.txt
# Копируем проект в рабочую директорию
COPY . .
# Команда для запуска бота0
CMD ["python", "main.py"]

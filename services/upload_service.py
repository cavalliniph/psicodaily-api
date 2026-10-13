from dotenv import load_dotenv
from io import BytesIO
from PIL import Image, ImageOps
import boto3
import os

load_dotenv()

# O r2.dev não redimensiona pela URL, então a foto já sobe no tamanho de exibição.
TAMANHO_MAXIMO_FOTO = (512, 512)

class UploadService():
	def __init__(self):
		self.s3 = boto3.client(
			service_name = 's3',
			endpoint_url = os.getenv('ENDPOINT_URL'),
			aws_access_key_id = os.getenv('ACCESS_KEY_ID'),
			aws_secret_access_key = os.getenv('SECRET_ACCESS_KEY'),
			region_name = 'auto'
		)
		# URL publica do bucket, nao e segredo; o .env so precisa dela se o bucket mudar
		self.url_publica = os.getenv('R2_PUBLIC_URL', 'https://pub-b6945a8ffa914112b679b4f615712e92.r2.dev').rstrip('/')

	def upload_file(self, imagem, id_usuario):
		upload_name = f"usuarios/{id_usuario}.jpg"

		# Reabrir com o Pillow também garante que o arquivo é mesmo uma imagem.
		foto = ImageOps.exif_transpose(Image.open(imagem)).convert('RGB')
		foto.thumbnail(TAMANHO_MAXIMO_FOTO)
		arquivo = BytesIO()
		foto.save(arquivo, 'JPEG', quality=85, optimize=True)
		arquivo.seek(0)

		self.s3.upload_fileobj(arquivo, 'psicodaily', upload_name, ExtraArgs={
			'ContentType': 'image/jpeg',
			# A chave não muda ao trocar a foto, então o navegador revalida pelo ETag.
			'CacheControl': 'no-cache',
		})

		print(f"uploaded {upload_name}")

	def url_foto_usuario(self, id_usuario):
		return f"{self.url_publica}/usuarios/{id_usuario}.jpg"

	def list_objects(self):
		res = self.s3.list_objects_v2(Bucket='psicodaily')
		for obj in res.get('Contents', []):
			print(f"Object: {obj}")

upload_service = UploadService()

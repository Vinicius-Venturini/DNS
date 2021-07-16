import socket
import re
import threading
from _thread import *
import mysql.connector

port = 53 #O serviço de DNS roda na porta 53, então não altere
ip = '' #Coloque seu endereço de ip local aqui
dns = ('8.8.8.8', 53)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((ip, port)) #Servidor escutando no IP selecionado e na porta 53

def getflags(flags):
	byte1 = bytes(flags[:1])
	byte2 = bytes(flags[1:2])
	rflags = ''
	QR = '1'
	opcode = ''
	for bit in range(1,5):
		opcode += str(ord(byte1)&(1<<bit))
	aa = '0'
	tc = '0'
	rd = '0'
	ra = '0'
	z = '000'
	rcode = '0101'

	return int(QR+opcode+aa+tc+rd, 2).to_bytes(1, byteorder='big')+int(ra+z+rcode, 2).to_bytes(1, byteorder='big')

def getquestiondomain(data):
	state = 0
	expectedlength = 0
	domainstring = ''
	domainparts = []
	x = 0
	y = 0
	for byte in data:
		if state == 1:
			domainstring += chr(byte)
			x += 1
			if x == expectedlength:
				domainparts.append(domainstring)
				domainstring = ''
				state = 0
				x = 0
		else:
			if byte == 0:
				break
			state = 1
			expectedlength = byte
		y += 1
	typeq = data[y+1:y+3]
	typen = data[y+3:y+5]
	final = 12+y+5
	return (domainparts, typeq, typen, final)

#Essa função, juntamente com as funções getquestiondomain e getflags, monta uma resposta de acessso negado, não vou entrar em detalhes pois é apenas uma resposta padrão do protocolo DNS. Se quiser entender mais sobre recomendo a leitura do RFC 1035.
def buildresponse(data):
	TransactionID = data[:2]
	flags = getflags(data[2:4])
	qdcount = b'\x00\x01'
	qdomain = getquestiondomain(data[12:])
	awcount = b'\x00\x00'
	authrr = b'\x00\x00'
	dnsheader = TransactionID+flags+qdcount+awcount+authrr+authrr+data[12:qdomain[3]]
	return (dnsheader)

#Essa função complementa a blackList, mas ao invés de verificar em uma database ele verifica utilizando REGEX.
def refilter(domain):
	listre = ["^beacons?[0-9]*[_.-]", "^ad([sxv]?[0-9]*|system)[_.-]([^.[:space:]]+\.){1,}|[_.-]ad([sxv]?[0-9]*|system)[_.-]", "^(.+[_.-])?adse?rv(er?|ice)?s?[0-9]*[_.-]", "^(.+[_.-])?telemetry[_.-]", "^adim(age|g)s?[0-9]*[_.-]", "^adtrack(er|ing)?[0-9]*[_.-]", "^advert(s|is(ing|ements?))?[0-9]*[_.-]", "^aff(iliat(es?|ion))?[_.-]", "^analytics?[_.-]", "^banners?[_.-]", "^count(ers?)?[0-9]*[_.-]", "^mads\.", "^pixels?[-.]", "^stat(s|istics)?[0-9]*[_.-]"]
	for i in range(len(listre)):
		result = re.search(listre[i], domain)
		if result != None:
			return 1
	return 0

#Função para conferir se um domínio está na blackList.
#Essa função utiliza mysql, então preencha com as credenciais do seu banco de dados.
#Crie uma nova tabela e insira os domínios disponibilizados no arquivo blackList.list.
def blackList(data, domain):
	mydb = mysql.connector.connect(
		host="",
		user="",
		password="",
		database=""
	)
	mycursor = mydb.cursor()
	if refilter(domain):
		return 1
	sql = "SELECT * FROM <insira o nome da sua tabela aqui> WHERE <insira a coluna de url aqui> = \'"
	sql += domain+"\'"
	mycursor.execute(sql)
	myresult = mycursor.fetchall()
	if len(myresult) == 0:
		return 0
	else:
		return 1

#Essa função retorna o domínio que o usuário quer acessar.
def getDomain(data):
	domain = getquestiondomain(data[12:])
	dm = ''
	for x in range(len(domain[0])):
		if x != 0:
			dm += '.'+domain[0][x]
		else:
			dm += domain[0][x]
	return dm

#Função principal, chamada quando é iniciada uma nova conexão.
def main(data, addr):
	domain = getDomain(data) #Armazena o Domínio que o usuário quer acessar.
	if blackList(data, domain): #Verifica se o Domínio requerido está na blackList.
		response = buildresponse(data) #Caso o domínio seja localizado na blackList, chama a função de gerar resposta de acesso negado.
		sock.sendto(response, addr) #Devolve a resposta para o usuário.
		print('{:<20s}{:^50s}{:>20s}'.format("BLOCKED", domain, addr[0]))
	else:
		fwd.sendto(data, dns) #Caso o domínio não esteja na blackList, o servidor fará uma requisição para o DNS do Google do domínio desejado.
		recv, dnsaddr = fwd.recvfrom(512)
		sock.sendto(recv, addr) #Retorna a resposta do Google DNS para o usuário.
		print('{:<20s}{:^50s}{:>20s}'.format("AUTHORIZED", domain, addr[0]))


print('-' * 90)
print('{:<20s}{:^50s}{:>20s}'.format("STATUS", "URL", "IP"))
print('-' * 90)
while 1:
	data, addr = sock.recvfrom(512)
	start_new_thread(main, (data, addr))

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import mysql.connector
import os

app = Flask(__name__)
CORS(app) 

# Utilisation des variables d'environnement pour cacher vos secrets sur GitHub
MOT_DE_PASSE_ADMIN = os.environ.get('ADMIN_PASS', 'IntelliSense')
JETON_SECRET = os.environ.get('SECRET_TOKEN', 'jeton_secret_ESPACElibre_2026')

db_config = {
    'host': os.environ.get('DB_HOST'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASS'),
    'database': os.environ.get('DB_NAME', 'defaultdb'),
    'port': int(os.environ.get('DB_PORT', 25060)),
    'ssl_disabled': False
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

# Route 1 : Récupérer tous les produits (Mise à jour avec catégorie)
@app.route('/api/produits', methods=['GET'])
def get_produits():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nom as name, prix as price, stock, image_url as image, categorie FROM produits")
    produits = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(produits)

# Route 2 : Recevoir et traiter une commande
@app.route('/api/commandes', methods=['POST'])
def creer_commande():
    data = request.json
    cart = data.get('cart', [])
    total = data.get('total', 0)
    
    # Nouvelles données récupérées
    methode = data.get('methode_paiement', 'Carte')
    client = data.get('client', {})

    if not cart:
        return jsonify({'error': 'Le panier est vide'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Créer l'entrée dans la table des commandes avec les infos du client
        cursor.execute(
            "INSERT INTO commandes (total, statut, nom_client, telephone, adresse, email, methode_paiement) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (total, 'En préparation', client.get('nom', ''), client.get('telephone', ''), client.get('adresse', ''), client.get('email', ''), methode)
        )
        commande_id = cursor.lastrowid
        
        # 2. Boucler sur le panier
        for item in cart:
            cursor.execute(
                "INSERT INTO lignes_commande (commande_id, produit_id, quantite, prix_unitaire) VALUES (%s, %s, %s, %s)",
                (commande_id, item['productId'], item['quantity'], item['price'])
            )
            cursor.execute(
                "UPDATE produits SET stock = stock - %s WHERE id = %s",
                (item['quantity'], item['productId'])
            )
        
        conn.commit() 
        return jsonify({'success': True, 'message': 'Commande enregistrée', 'commande_id': commande_id}), 201
        
    except Exception as e:
        conn.rollback() 
        return jsonify({'success': False, 'error': str(e)}), 500
        
    finally:
        cursor.close()
        conn.close()

# Route 3 : Ajouter un nouveau produit (Zone Admin)
@app.route('/api/produits', methods=['POST'])
def ajouter_produit():
    token_recu = request.headers.get('Authorization')
    if token_recu != f"Bearer {JETON_SECRET}":
        return jsonify({'success': False, 'error': 'Accès refusé'}), 403
        
    data = request.json
    nom = data.get('nom')
    prix = data.get('prix')
    stock = data.get('stock')
    image_url = data.get('image_url')
    categorie = data.get('categorie', 'Autre') # Nouvelle ligne

    if not all([nom, prix, stock, image_url]):
        return jsonify({'error': 'Données manquantes'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO produits (nom, prix, stock, image_url, categorie) VALUES (%s, %s, %s, %s, %s)",
            (nom, prix, stock, image_url, categorie)
        )
        conn.commit() 
        return jsonify({'success': True, 'message': 'Produit ajouté avec succès'}), 201
    except Exception as e:
        conn.rollback() 
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# Route 4 : Récupérer toutes les commandes (Espace Admin)
@app.route('/api/commandes', methods=['GET'])
def get_commandes():
    # Sécurisation ajoutée
    token_recu = request.headers.get('Authorization')
    if token_recu != f"Bearer {JETON_SECRET}":
        return jsonify({'success': False, 'error': 'Accès refusé'}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM commandes ORDER BY date_commande DESC")
    commandes = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(commandes)

# Route 5 : Supprimer un produit (Espace Admin)
@app.route('/api/produits/<int:id>', methods=['DELETE'])
def supprimer_produit(id):
    token_recu = request.headers.get('Authorization')
    if token_recu != f"Bearer {JETON_SECRET}":
        return jsonify({'success': False, 'error': 'Accès refusé'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Supprimer d'abord les lignes de commandes liées pour éviter les erreurs de clés étrangères
        cursor.execute("DELETE FROM lignes_commande WHERE produit_id = %s", (id,))
        cursor.execute("DELETE FROM produits WHERE id = %s", (id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Produit supprimé'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if data and data.get('password') == MOT_DE_PASSE_ADMIN:
        return jsonify({'success': True, 'token': JETON_SECRET})
    return jsonify({'success': False, 'error': 'Mot de passe incorrect'}), 401

# Route 6 : Modifier le statut d'une commande (Espace Admin)
@app.route('/api/commandes/<int:id>/statut', methods=['PUT'])
def modifier_statut_commande(id):
    # Vérification de sécurité
    token_recu = request.headers.get('Authorization')
    if token_recu != f"Bearer {JETON_SECRET}":
        return jsonify({'success': False, 'error': 'Accès refusé'}), 403

    data = request.json
    nouveau_statut = data.get('statut')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE commandes SET statut = %s WHERE id = %s", (nouveau_statut, id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Statut mis à jour'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/')
def accueil():
    return send_file('botique.html')

        
if __name__ == '__main__':
    # Lance le serveur sur le port 5001
    app.run(debug=True, port=5001)

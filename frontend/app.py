from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import requests
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    admin_mode = request.args.get('admin') == 'true'
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            response = requests.post(f"{BACKEND_URL}/login", json={
                "username": username,
                "password": password
            })
            
            if response.status_code == 200:
                data = response.json()
                session['access_token'] = data['access_token']
                session['user'] = data['user']
                flash('Connexion réussie!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Identifiants incorrects', 'error')
        except requests.exceptions.RequestException:
            flash('Erreur de connexion au serveur', 'error')
    
    return render_template('login.html', admin_mode=admin_mode)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        try:
            response = requests.post(f"{BACKEND_URL}/register", json={
                "username": username,
                "email": email,
                "password": password
            })
            
            if response.status_code == 200:
                flash('Inscription réussie! Vous pouvez maintenant vous connecter.', 'success')
                return redirect(url_for('login'))
            else:
                error_data = response.json()
                flash(error_data.get('detail', 'Erreur lors de l\'inscription'), 'error')
        except requests.exceptions.RequestException:
            flash('Erreur de connexion au serveur', 'error')
    
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = session['user']
    
    # Récupérer les annonces
    try:
        jobs_response = requests.get(f"{BACKEND_URL}/jobs")
        jobs = jobs_response.json() if jobs_response.status_code == 200 else []
    except:
        jobs = []
    
    return render_template('dashboard.html', user=user, jobs=jobs)

@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or session['user']['role'] != 'admin':
        flash('Accès non autorisé', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        
        users_response = requests.get(f"{BACKEND_URL}/users")
        users = users_response.json() if users_response.status_code == 200 else []
        
    
        jobs_response = requests.get(f"{BACKEND_URL}/jobs")
        jobs = jobs_response.json() if jobs_response.status_code == 200 else []
        
        
        headers = {'Authorization': f"Bearer {session.get('access_token')}"}
        apps_response = requests.get(f"{BACKEND_URL}/applications", headers=headers)
        applications = apps_response.json() if apps_response.status_code == 200 else []
        
    except:
        users = []
        jobs = []
        applications = []
    
    return render_template('admin.html', users=users, jobs=jobs, applications=applications)

@app.route('/add_job', methods=['GET', 'POST'])
def add_job():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        job_data = {
            "title": request.form['title'],
            "description": request.form['description'],
            "company": request.form['company'],
            "location": request.form['location'],
            "salary": float(request.form['salary']) if request.form['salary'] else None
        }
        
        try:
            headers = {'Authorization': f"Bearer {session.get('access_token')}"}
            response = requests.post(f"{BACKEND_URL}/jobs", json=job_data, headers=headers)
            
            if response.status_code == 200:
                flash('Annonce créée avec succès!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Erreur lors de la création de l\'annonce', 'error')
        except requests.exceptions.RequestException:
            flash('Erreur de connexion au serveur', 'error')
    
    return render_template('add_job.html')

@app.route('/apply_job/<int:job_id>', methods=['GET', 'POST'])
def apply_job(job_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Vérifier si un fichier a été uploadé
        if 'cv_file' not in request.files:
            flash('Veuillez sélectionner un fichier CV', 'error')
            return render_template('apply_job.html', job_id=job_id)
        
        cv_file = request.files['cv_file']
        if cv_file.filename == '':
            flash('Veuillez sélectionner un fichier CV', 'error')
            return render_template('apply_job.html', job_id=job_id)
        
        if not cv_file.filename.lower().endswith('.pdf'):
            flash('Seuls les fichiers PDF sont acceptés', 'error')
            return render_template('apply_job.html', job_id=job_id)
        
        try:
            # Envoyer le fichier et les données
            files = {'cv_file': (cv_file.filename, cv_file, 'application/pdf')}
            data = {
                'cover_letter': request.form['cover_letter'],
                'user_id': session['user']['id']
            }
            
            headers = {'Authorization': f"Bearer {session.get('access_token')}"}
            response = requests.post(
                f"{BACKEND_URL}/jobs/{job_id}/apply", 
                files=files,
                data=data,
                headers=headers
            )
            
            if response.status_code == 200:
                flash('Candidature envoyée avec succès!', 'success')
                return redirect(url_for('dashboard'))
            else:
                error_data = response.json()
                flash(error_data.get('detail', 'Erreur lors de l\'envoi de la candidature'), 'error')
        except requests.exceptions.RequestException:
            flash('Erreur de connexion au serveur', 'error')
    
    return render_template('apply_job.html', job_id=job_id)

@app.route('/admin/applications/<int:job_id>')
def view_applications(job_id):
    if 'user' not in session or session['user']['role'] != 'admin':
        flash('Accès non autorisé', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        headers = {'Authorization': f"Bearer {session.get('access_token')}"}
        response = requests.get(f"{BACKEND_URL}/jobs/{job_id}/applications", headers=headers)
        applications = response.json() if response.status_code == 200 else []
    except:
        applications = []
    
    return render_template('job_applications.html', applications=applications, job_id=job_id)

@app.route('/delete_job/<int:job_id>')
def delete_job(job_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        headers = {'Authorization': f"Bearer {session.get('access_token')}"}
        response = requests.delete(f"{BACKEND_URL}/jobs/{job_id}", headers=headers)
        
        if response.status_code == 200:
            flash('Annonce supprimée avec succès!', 'success')
        else:
            flash('Erreur lors de la suppression de l\'annonce', 'error')
    except requests.exceptions.RequestException:
        flash('Erreur de connexion au serveur', 'error')
    
    if session['user']['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('dashboard'))

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'user' not in session or session['user']['role'] != 'admin':
        flash('Accès non autorisé', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        headers = {'Authorization': f"Bearer {session.get('access_token')}"}
        response = requests.delete(f"{BACKEND_URL}/users/{user_id}", headers=headers)
        
        if response.status_code == 200:
            flash('Utilisateur supprimé avec succès!', 'success')
        else:
            flash('Erreur lors de la suppression de l\'utilisateur', 'error')
    except requests.exceptions.RequestException:
        flash('Erreur de connexion au serveur', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Déconnexion réussie', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
from app.extensions import db


class Print3DJob(db.Model):
    __tablename__ = "print3d_jobs"

    id = db.Column(db.Integer, primary_key=True)

    requester_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    requester_user = db.relationship("User", backref="print3d_jobs")

    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)

    file_ref = db.Column(db.Text, nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size_bytes = db.Column(db.Integer, nullable=False)

    status = db.Column(db.String(30), nullable=False, default="REQUESTED", index=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now(), nullable=True)

    def __repr__(self) -> str:
        return f"<Print3DJob {self.id} requester={self.requester_user_id} status={self.status}>"

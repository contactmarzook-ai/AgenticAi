--- backend/app/models.py
+++ backend/app/models.py
@@ -62,7 +62,8 @@
     name: Mapped[str] = mapped_column(String, index=True)
     description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
     user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
-    steps_json: Mapped[list] = mapped_column(JSON, default=list)
+    definition: Mapped[dict] = mapped_column(JSON, default=dict) # Stores nodes, edges, context
+    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

     user: Mapped["User"] = relationship(back_populates="workflows")

--- backend/app/models.py
+++ backend/app/models.py
@@ -52,6 +52,7 @@
     trigger_keywords: Mapped[Optional[str]] = mapped_column(String, nullable=True)
     handler: Mapped[str] = mapped_column(String)
     input_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
+    output_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
     is_active: Mapped[bool] = mapped_column(Boolean, default=True)
     created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

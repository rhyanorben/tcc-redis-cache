package br.edu.tcc.pedidos.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.OffsetDateTime;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.SourceType;

@Entity
@Table(name = "cliente", uniqueConstraints = @UniqueConstraint(columnNames = {"tenant_id", "id"}))
public class Cliente {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, length = 160)
    private String nome;

    @CreationTimestamp(source = SourceType.DB)
    @Column(name = "criado_em", nullable = false, updatable = false)
    private OffsetDateTime criadoEm;

    protected Cliente() {
    }

    public Cliente(long tenantId, String nome) {
        this.tenantId = tenantId;
        this.nome = nome;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getNome() {
        return nome;
    }

    public OffsetDateTime getCriadoEm() {
        return criadoEm;
    }
}

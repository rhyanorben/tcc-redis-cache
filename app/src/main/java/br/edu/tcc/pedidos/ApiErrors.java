package br.edu.tcc.pedidos;

import jakarta.validation.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler({ConstraintViolationException.class, MethodArgumentNotValidException.class})
    public ProblemDetail tratarValidacaoInvalida(Exception exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Confira os campos, a empresa e os limites de paginação.");
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ProblemDetail tratarConflitoIntegridade(DataIntegrityViolationException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "A operação viola uma restrição de integridade.");
    }
}

// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title USDC-mock — ERC-20 de prueba para el entorno de evaluación
/// @notice Token ERC-20 mínimo con 6 decimales (igual que el USDC real) y una
///         función `mint` PÚBLICA para que el harness de evaluación pueda fondear
///         cuentas y direcciones de depósito sin permisos. NO usar fuera del
///         entorno local de evaluación.
/// @dev    Coincide con lo que la spec exige del activo quote
///         (spec/00-fundaciones/activos-y-par-de-trading.md §2.2): ERC-20,
///         símbolo USDC, 6 decimales. La dirección del contrato desplegado es el
///         parámetro de entorno que consumen las épicas 06/07/08.
contract UsdcMock {
    string public constant name = "USD Coin (mock)";
    string public constant symbol = "USDC";
    uint8 public constant decimals = 6;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    /// @notice Emite `value` unidades mínimas (10^-6 USDC) a la cuenta `to`.
    ///         Abierta a cualquiera: es un mock exclusivo del entorno de evaluación.
    function mint(address to, uint256 value) external {
        require(to != address(0), "mint to zero address");
        totalSupply += value;
        balanceOf[to] += value;
        emit Transfer(address(0), to, value);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        return _transfer(msg.sender, to, value);
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 permitido = allowance[from][msg.sender];
        require(permitido >= value, "insufficient allowance");
        if (permitido != type(uint256).max) {
            allowance[from][msg.sender] = permitido - value;
        }
        return _transfer(from, to, value);
    }

    function _transfer(address from, address to, uint256 value) internal returns (bool) {
        require(to != address(0), "transfer to zero address");
        uint256 saldo = balanceOf[from];
        require(saldo >= value, "insufficient balance");
        unchecked {
            balanceOf[from] = saldo - value;
        }
        balanceOf[to] += value;
        emit Transfer(from, to, value);
        return true;
    }
}

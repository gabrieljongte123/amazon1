import { useState, useCallback } from 'react';
import { addToCart as addToCartApi } from '../services/api';
import type { CartResponse } from '../types';

interface UseCartReturn {
  addToCart: (productId: string, quantity?: number) => Promise<CartResponse | null>;
  isLoading: boolean;
  error: string | null;
  cartItem: CartResponse | null;
}

export function useCart(): UseCartReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cartItem, setCartItem] = useState<CartResponse | null>(null);

  const addToCart = useCallback(
    async (productId: string, quantity: number = 1): Promise<CartResponse | null> => {
      setIsLoading(true);
      setError(null);
      setCartItem(null);

      try {
        const response = await addToCartApi(productId, quantity);
        setCartItem(response);
        return response;
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'Failed to add item to cart. Please try again.';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  return { addToCart, isLoading, error, cartItem };
}

export default useCart;

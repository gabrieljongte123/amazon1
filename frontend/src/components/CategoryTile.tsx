import { useNavigate } from 'react-router-dom';

interface CategoryTileProps {
  name: string;
  emoji: string;
}

function CategoryTile({ name, emoji }: CategoryTileProps) {
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/chat?category=${encodeURIComponent(name)}`);
  };

  return (
    <button className="category-tile" onClick={handleClick} aria-label={`Shop ${name}`}>
      <span className="category-tile__emoji" aria-hidden="true">
        {emoji}
      </span>
      <span className="category-tile__name">{name}</span>
    </button>
  );
}

export default CategoryTile;
